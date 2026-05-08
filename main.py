import json
import re
import time
from datetime import datetime, timezone, timedelta

import httpx
from astrbot.api.event import AstrMessageEvent, filter
from astrbot.api.star import Context, Star, register

TZ = timezone(timedelta(hours=8))

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
}

# Game configurations
GAMES = {
    "gs": {
        "uid": 75276550,
        "keywords": ["版本前瞻特别节目"],
        "name": "原神",
        "biz": "hk4e",
        "cmds": ["gicode", "原神兑换码"],
    },
    "sr": {
        "uid": 80823548,
        "keywords": ["版本前瞻讨论活动", "版本前瞻特别节目"],
        "name": "崩坏：星穹铁道",
        "biz": "hkrpg",
        "cmds": ["hsrcode", "崩铁兑换码"],
    },
    "zzz": {
        "uid": 152039072,
        "keywords": ["版本前瞻特别节目", "版本前瞻"],
        "name": "绝区零",
        "biz": "nap",
        "cmds": ["zzzcode", "绝区零兑换码"],
    },
}


@register(
    "astrbot_plugin_gscode",
    "yxm11",
    "获取米哈游游戏（原神/星穹铁道/绝区零）前瞻直播兑换码",
    "1.0.0",
)
class GsCodePlugin(Star):
    def __init__(self, context: Context):
        super().__init__(context)
        self.client = httpx.AsyncClient(timeout=15)

    # ─── miHoYo API Pipeline ─────────────────────────────────────────────

    async def _get_act_id(self, game_key: str) -> str:
        """Discover livestream act_id from official miyoushe posts."""
        config = GAMES[game_key]
        url = (
            f"https://bbs-api.mihoyo.com/painter/api/user_instant/list"
            f"?offset=0&size=20&uid={config['uid']}"
        )
        resp = await self.client.get(url, headers=HEADERS)
        data = resp.json()
        if data.get("retcode") != 0:
            return ""

        act_id = ""
        for item in data["data"]["list"]:
            post = item.get("post", {}).get("post", {})
            if not post:
                continue
            subject = post.get("subject", "")
            if not any(kw in subject for kw in config["keywords"]):
                continue

            sc = post.get("structured_content", "")
            if not sc:
                continue
            try:
                segments = json.loads(sc)
                for seg in segments:
                    link = seg.get("attributes", {}).get("link", "")
                    if "act_id=" in link:
                        match = re.findall(r"act_id=(.*?)&", link)
                        if match:
                            act_id = match[0]
                            break
            except (json.JSONDecodeError, KeyError):
                pass
            if act_id:
                break
        return act_id

    async def _get_live_data(self, act_id: str) -> dict:
        """Fetch livestream metadata from miyolive API."""
        resp = await self.client.get(
            "https://api-takumi.mihoyo.com/event/miyolive/index",
            headers={**HEADERS, "x-rpc-act_id": act_id},
        )
        data = resp.json()
        if data.get("retcode") != 0:
            return {
                "error": data.get("message", "Unknown error"),
                "retcode": data.get("retcode"),
            }

        live = data["data"]["live"]
        template = json.loads(data["data"].get("template", "{}"))

        result = {
            "code_ver": live.get("code_ver", ""),
            "title": live.get("title", "").replace("特别节目", ""),
            "is_end": live.get("is_end", False),
            "start": live.get("start", ""),
            "header": template.get("kvDesktop", ""),
            "room": template.get("liveConfig", [{}])[0].get("desktop", ""),
        }

        if live.get("is_end"):
            review = template.get("reviewUrl", "")
            if isinstance(review, dict):
                review = review.get("args", {}).get("post_id", "")
            result["review"] = review
        else:
            now = datetime.now(TZ)
            start_str = live.get("start", "")
            if start_str:
                try:
                    start_dt = datetime.strptime(start_str, "%Y-%m-%d %H:%M:%S").replace(tzinfo=TZ)
                    if now < start_dt:
                        result["not_started"] = True
                except ValueError:
                    pass
        return result

    async def _get_codes(self, version: str, act_id: str) -> list:
        """Fetch redemption codes from refreshCode API."""
        resp = await self.client.get(
            "https://api-takumi-static.mihoyo.com/event/miyolive/refreshCode",
            params={"version": version, "time": str(int(time.time()))},
            headers={**HEADERS, "x-rpc-act_id": act_id},
        )
        data = resp.json()
        if data.get("retcode") != 0:
            return []
        codes = []
        for item in data["data"].get("code_list", []):
            title = re.sub(r"<.*?>", "", item["title"].replace("&nbsp;", " "))
            codes.append({"title": title, "code": item["code"]})
        return codes

    # ─── Command Handler ─────────────────────────────────────────────────

    async def _handle_code(self, event: AstrMessageEvent, game_key: str):
        """Shared handler for all game code commands."""
        config = GAMES[game_key]

        # Step 1: Find act_id
        try:
            act_id = await self._get_act_id(game_key)
        except Exception as e:
            yield event.plain_result(f"获取活动信息失败：{e}")
            return

        if not act_id:
            yield event.plain_result(f"暂无{config['name']}前瞻直播资讯！")
            return

        # Step 2: Get live data
        try:
            live = await self._get_live_data(act_id)
        except Exception as e:
            yield event.plain_result(f"获取直播数据失败：{e}")
            return

        if live.get("error"):
            retcode = live.get("retcode", "")
            if retcode == -500007:
                yield event.plain_result(f"{config['name']}前瞻直播活动已结束，兑换码可能已过期。")
            else:
                yield event.plain_result(f"直播数据异常：{live['error']}")
            return

        title = live.get("title", config["name"])

        # Not started yet
        if live.get("not_started"):
            msg = f"📺 {title}\n\n直播尚未开始\n预计开播：{live.get('start', '未知')}"
            if live.get("header"):
                yield event.image_result(live["header"])
            yield event.plain_result(msg)
            return

        # Step 3: Fetch codes
        try:
            codes = await self._get_codes(live["code_ver"], act_id)
        except Exception as e:
            yield event.plain_result(f"获取兑换码失败：{e}")
            return

        if not codes:
            yield event.plain_result(f"暂未发布{config['name']}兑换码，请稍后再试。\n* 官方接口有约2分钟延迟")
            return

        # Build response
        lines = [f"🎮 {title}", f"当前发布 {len(codes)} 个兑换码，请在有效期内及时兑换：\n"]
        for c in codes:
            lines.append(f"【{c['title']}】\n{c['code']}\n")
        lines.append("* 兑换码有效期有限，请尽快使用")

        if live.get("review"):
            lines.append(f"\n📺 直播回放：https://www.miyoushe.com/ys/article/{live['review']}")

        yield event.plain_result("\n".join(lines))

    # ─── Register Commands ───────────────────────────────────────────────

    @filter.command("gicode", aliases=["原神兑换码"])
    async def gicode(self, event: AstrMessageEvent):
        """获取原神前瞻直播兑换码"""
        async for resp in self._handle_code(event, "gs"):
            yield resp

    @filter.command("hsrcode", aliases=["崩铁兑换码"])
    async def hsrcode(self, event: AstrMessageEvent):
        """获取崩坏：星穹铁道前瞻直播兑换码"""
        async for resp in self._handle_code(event, "sr"):
            yield resp

    @filter.command("zzzcode", aliases=["绝区零兑换码"])
    async def zzzcode(self, event: AstrMessageEvent):
        """获取绝区零前瞻直播兑换码"""
        async for resp in self._handle_code(event, "zzz"):
            yield resp

    @filter.command("兑换码", aliases=["redeemcode"])
    async def allcodes(self, event: AstrMessageEvent):
        """获取所有游戏的前瞻直播兑换码"""
        for game_key in GAMES:
            async for resp in self._handle_code(event, game_key):
                yield resp

    async def terminate(self):
        await self.client.aclose()
