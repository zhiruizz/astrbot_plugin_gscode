import hashlib
import json
import re
import time
import uuid
import urllib.parse
from datetime import datetime, timezone, timedelta

import httpx
from astrbot.api.event import AstrMessageEvent, filter
from astrbot.api.star import Context, Star, register

TZ = timezone(timedelta(hours=8))

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
}

BILI_HEADERS = {
    **HEADERS,
    "Referer": "https://www.bilibili.com",
}

# Game configurations
GAMES = {
    "gs": {
        "uid": 75276539,
        "keywords": ["版本前瞻特别节目", "前瞻"],
        "name": "原神",
        "search_kw": "原神兑换码",
    },
    "sr": {
        "uid": 80823548,
        "keywords": ["版本前瞻讨论活动", "版本前瞻特别节目"],
        "name": "崩坏：星穹铁道",
        "search_kw": "崩坏星穹铁道兑换码",
    },
    "zzz": {
        "uid": 152039148,
        "keywords": ["版本前瞻特别节目", "版本前瞻"],
        "name": "绝区零",
        "search_kw": "绝区零兑换码",
    },
}

MIXIN_KEY_ENC_TAB = [
    46, 47, 18, 2, 53, 8, 23, 32, 15, 50, 10, 31, 58, 3, 45, 35,
    27, 43, 5, 49, 33, 9, 42, 19, 29, 28, 14, 39, 12, 38, 41, 13,
    37, 48, 7, 16, 24, 55, 40, 61, 26, 17, 0, 1, 60, 51, 30, 4,
    22, 25, 54, 21, 56, 59, 6, 63, 57, 62, 11, 36, 20, 34, 44, 52,
]

# Code parsing patterns
CODE_ALPHA = re.compile(r"\b[A-Z0-9]{10,16}\b")
CODE_CN = re.compile(r"^[一-鿿㐀-䶿]{4,15}$")
SECTION_HEADER = re.compile(
    r"^([\d一二三四五六七八九十]+[.、．\s]*第[一二三四五六七八九十\d]+[组个]|"
    r"第[一二三四五六七八九十\d]+[组个]|兑换码|CODE|code|激活码|礼包码|"
    r"版本信息|版本前瞻|上半|下半|前瞻直播|直播兑换|前瞻兑换|"
    r"以上.*信息|信息汇总|总结|注意|PS|ps|截止|"
    r"卡池信息|月之七前瞻|"
    r"以上.*码|兑换码.*信息|前瞻.*信息)"
)


def _parse_codes_from_text(text: str) -> list:
    codes = []
    lines = [line.strip() for line in text.split("\n") if line.strip()]
    for i, line in enumerate(lines):
        if SECTION_HEADER.match(line) or len(line) < 2:
            continue
        code = None
        title = ""
        alpha_match = CODE_ALPHA.search(line)
        if alpha_match:
            code = alpha_match.group()
            for j in range(max(0, i - 3), i):
                if CODE_CN.match(lines[j].strip()) and not SECTION_HEADER.match(lines[j].strip()):
                    title = lines[j].strip()
                    break
        elif CODE_CN.match(line) and not SECTION_HEADER.match(line):
            code = line
            for j in range(max(0, i - 3), i):
                c = lines[j].strip()
                if re.match(r"^[\d一二三四五六七八九十]+[.、．\s]*第[一二三四五六七八九十\d]+[组个]", c):
                    title = c
                    break
                elif re.match(r"^第[一二三四五六七八九十\d]+[组个]", c):
                    title = c
                    break
        if code:
            codes.append({"title": title, "code": code})
    seen = {}
    for item in codes:
        if item["code"] not in seen:
            seen[item["code"]] = item
    return list(seen.values())


@register(
    "astrbot_plugin_gscode",
    "yxm11",
    "获取米哈游游戏（原神/星穹铁道/绝区零）前瞻直播兑换码",
    "1.1.0",
)
class GsCodePlugin(Star):
    def __init__(self, context: Context):
        super().__init__(context)
        self.client = httpx.AsyncClient(timeout=15)
        self.wbi_img_key = ""
        self.wbi_sub_key = ""
        self._bili_initialized = False

    # ─── Bilibili Session Init ────────────────────────────────────────────

    async def _init_bilibili(self):
        if self._bili_initialized:
            return
        buvid3 = str(uuid.uuid4()) + "infoc"
        self.client.cookies.set("buvid3", buvid3, domain=".bilibili.com")
        self.client.cookies.set("b_nut", str(int(time.time())), domain=".bilibili.com")
        try:
            resp = await self.client.get("https://api.bilibili.com/x/frontend/finger/spi", headers=BILI_HEADERS)
            spi = resp.json()
            if spi.get("code") == 0:
                if spi["data"].get("b_3"):
                    self.client.cookies.set("buvid3", spi["data"]["b_3"], domain=".bilibili.com")
                if spi["data"].get("b_4"):
                    self.client.cookies.set("buvid4", spi["data"]["b_4"], domain=".bilibili.com")
        except Exception:
            pass
        try:
            resp = await self.client.get("https://api.bilibili.com/x/web-interface/nav", headers=BILI_HEADERS)
            nav = resp.json()["data"]
            self.wbi_img_key = nav["wbi_img"]["img_url"].rsplit("/", 1)[1].split(".")[0]
            self.wbi_sub_key = nav["wbi_img"]["sub_url"].rsplit("/", 1)[1].split(".")[0]
        except Exception:
            pass
        self._bili_initialized = True

    def _sign_wbi(self, params: dict) -> dict:
        mixin_key = "".join((self.wbi_img_key + self.wbi_sub_key)[i] for i in MIXIN_KEY_ENC_TAB)[:32]
        params["wts"] = int(time.time())
        params = dict(sorted(params.items()))
        params_str = urllib.parse.urlencode(
            {k: "".join(c for c in str(v) if c.isascii()) for k, v in params.items()}
        )
        params["w_rid"] = hashlib.md5((params_str + mixin_key).encode()).hexdigest()
        return params

    # ─── miyolive API (Primary) ──────────────────────────────────────────

    async def _get_act_id(self, game_key: str) -> str:
        config = GAMES[game_key]
        url = f"https://bbs-api.mihoyo.com/painter/api/user_instant/list?offset=0&size=20&uid={config['uid']}"
        resp = await self.client.get(url, headers=HEADERS)
        data = resp.json()
        if data.get("retcode") != 0:
            return ""
        for item in data["data"]["list"]:
            post = item.get("post", {}).get("post", {})
            if not post:
                continue
            if not any(kw in post.get("subject", "") for kw in config["keywords"]):
                continue
            sc = post.get("structured_content", "")
            if not sc:
                continue
            try:
                for seg in json.loads(sc):
                    link = seg.get("attributes", {}).get("link", "")
                    if "act_id=" in link:
                        match = re.findall(r"act_id=(.*?)&", link)
                        if match:
                            return match[0]
            except (json.JSONDecodeError, KeyError):
                pass
        return ""

    async def _get_codes_from_miyolive(self, game_key: str) -> dict:
        config = GAMES[game_key]
        try:
            act_id = await self._get_act_id(game_key)
        except Exception:
            return {"status": "error"}
        if not act_id:
            return {"status": "no_act_id"}

        try:
            resp = await self.client.get(
                "https://api-takumi.mihoyo.com/event/miyolive/index",
                headers={**HEADERS, "x-rpc-act_id": act_id},
            )
            data = resp.json()
        except Exception:
            return {"status": "error"}

        if data.get("retcode") != 0:
            return {"status": "ended"}

        live = data["data"]["live"]
        ver = live.get("code_ver", "")
        title = live.get("title", "").replace("特别节目", "")

        # Try to fetch codes regardless of is_end status
        try:
            resp2 = await self.client.get(
                "https://api-takumi-static.mihoyo.com/event/miyolive/refreshCode",
                params={"version": ver, "time": str(int(time.time()))},
                headers={**HEADERS, "x-rpc-act_id": act_id},
            )
            data2 = resp2.json()
            if data2.get("retcode") == 0:
                codes = []
                for item in data2["data"].get("code_list", []):
                    t = re.sub(r"<.*?>", "", item["title"].replace("&nbsp;", " "))
                    codes.append({"title": t, "code": item["code"]})
                if codes:
                    return {"status": "ok", "codes": codes, "title": title}
        except Exception:
            pass
        return {"status": "ended"}

    # ─── Bilibili Fallback ────────────────────────────────────────────────

    async def _get_codes_from_bilibili(self, game_key: str) -> dict:
        config = GAMES[game_key]
        await self._init_bilibili()

        if not self.wbi_img_key:
            return {"status": "error", "codes": []}

        params = self._sign_wbi({
            "search_type": "video",
            "keyword": config["search_kw"],
            "order": "pubdate",
            "page": 1,
        })
        try:
            resp = await self.client.get(
                "https://api.bilibili.com/x/web-interface/wbi/search/type",
                params=params, headers=BILI_HEADERS,
            )
            videos = resp.json().get("data", {}).get("result", [])[:3]
        except Exception:
            return {"status": "error", "codes": []}

        if not videos:
            return {"status": "no_videos", "codes": []}

        all_codes = []
        source_title = ""
        for video in videos:
            bvid = video.get("bvid", "")
            title = video.get("title", "").replace('<em class="keyword">', "").replace("</em>", "")

            try:
                resp2 = await self.client.get(
                    "https://api.bilibili.com/x/web-interface/view",
                    params={"bvid": bvid}, headers=BILI_HEADERS,
                )
                aid = resp2.json()["data"]["aid"]
            except Exception:
                continue

            for pn in range(1, 4):
                try:
                    resp3 = await self.client.get(
                        "https://api.bilibili.com/x/v2/reply",
                        params={"type": 1, "oid": aid, "sort": 2, "pn": pn, "ps": 20},
                        headers=BILI_HEADERS,
                    )
                    d3 = resp3.json()
                    if d3.get("code") != 0:
                        break
                    replies = d3.get("data", {}).get("replies")
                    if not replies:
                        break
                    for r in replies:
                        content = r["content"]["message"]
                        codes = _parse_codes_from_text(content)
                        if codes:
                            all_codes.extend(codes)
                            if not source_title:
                                source_title = title
                except Exception:
                    break
                await self._sleep(0.3)

            await self._sleep(0.5)

        seen = {}
        for item in all_codes:
            if item["code"] not in seen:
                seen[item["code"]] = item
        return {"status": "ok" if seen else "no_codes", "codes": list(seen.values()), "title": source_title}

    @staticmethod
    async def _sleep(seconds: float):
        import asyncio
        await asyncio.sleep(seconds)

    # ─── Main Handler ────────────────────────────────────────────────────

    async def _handle_code(self, event: AstrMessageEvent, game_key: str):
        config = GAMES[game_key]

        # Primary: miyolive
        miyolive = await self._get_codes_from_miyolive(game_key)
        if miyolive["status"] == "ok":
            codes = miyolive["codes"]
            title = miyolive.get("title", config["name"])
            lines = [f"🎮 {config['name']}兑换码查询结果"]
            lines.append(f"来源：{title}")
            lines.append(f"共找到 {len(codes)} 个兑换码，请在有效期内及时兑换：\n")
            for c in codes:
                t = f"【{c['title']}】" if c["title"] else ""
                lines.append(f"{t}\n{c['code']}\n")
            lines.append("* 兑换码有效期有限，请尽快使用")
            yield event.plain_result("\n".join(lines))
            return

        # Fallback: Bilibili
        bili = await self._get_codes_from_bilibili(game_key)
        if bili["status"] == "ok":
            codes = bili["codes"]
            title = bili.get("title", "")
            lines = [f"🎮 {config['name']}兑换码查询结果"]
            if title:
                lines.append(f"来源：{title}")
            lines.append(f"共找到 {len(codes)} 个兑换码，请在有效期内及时兑换：\n")
            for c in codes:
                t = f"【{c['title']}】" if c["title"] else ""
                lines.append(f"{t}\n{c['code']}\n")
            lines.append("* 兑换码有效期有限，请尽快使用")
            lines.append("\n数据来源：B站评论区")
            yield event.plain_result("\n".join(lines))
            return

        # Nothing found
        yield event.plain_result(
            f"🎮 {config['name']}兑换码查询结果\n"
            f"❌ 暂无前瞻直播资讯\n\n"
            f"当前没有正在进行的{config['name']}前瞻直播。\n"
            f"新版本前瞻通常在版本更新前1-2周举行，届时再查询即可。"
        )

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

    # ─── Regex Auto-Trigger (group chat) ─────────────────────────────────

    @filter.regex(r"原神.{0,5}兑换码|原神.{0,3}前瞻.{0,3}码")
    async def auto_genshin(self, event: AstrMessageEvent):
        """群聊自动识别：原神兑换码"""
        async for resp in self._handle_code(event, "gs"):
            yield resp

    @filter.regex(r"(崩铁|星穹铁道|星铁|铁道).{0,5}兑换码|(崩铁|星穹铁道|星铁).{0,3}前瞻.{0,3}码")
    async def auto_hsr(self, event: AstrMessageEvent):
        """群聊自动识别：崩铁兑换码"""
        async for resp in self._handle_code(event, "sr"):
            yield resp

    @filter.regex(r"绝区零.{0,5}兑换码|绝区零.{0,3}前瞻.{0,3}码|zzz.{0,5}(code|兑换码)")
    async def auto_zzz(self, event: AstrMessageEvent):
        """群聊自动识别：绝区零兑换码"""
        async for resp in self._handle_code(event, "zzz"):
            yield resp

    @filter.regex(r"(?<!\w)(有.{0,3}兑换码|兑换码.{0,5}(查|有|给|发|来|求|要|在哪|怎么|有没有))")
    async def auto_all(self, event: AstrMessageEvent):
        """群聊自动识别：有兑换码吗 / 兑换码怎么查"""
        for game_key in GAMES:
            async for resp in self._handle_code(event, game_key):
                yield resp

    # ─── LLM Tool Registration ───────────────────────────────────────────

    @filter.llm_tool("get_genshin_code")
    async def tool_genshin(self, event: AstrMessageEvent):
        """获取原神最新前瞻直播兑换码。当用户询问原神兑换码、原神前瞻直播码时调用。"""
        async for resp in self._handle_code(event, "gs"):
            yield resp

    @filter.llm_tool("get_hsr_code")
    async def tool_hsr(self, event: AstrMessageEvent):
        """获取崩坏：星穹铁道最新前瞻直播兑换码。当用户询问崩铁/星铁/星穹铁道兑换码时调用。"""
        async for resp in self._handle_code(event, "sr"):
            yield resp

    @filter.llm_tool("get_zzz_code")
    async def tool_zzz(self, event: AstrMessageEvent):
        """获取绝区零最新前瞻直播兑换码。当用户询问绝区零/ZZZ兑换码时调用。"""
        async for resp in self._handle_code(event, "zzz"):
            yield resp

    @filter.llm_tool("get_all_codes")
    async def tool_all(self, event: AstrMessageEvent):
        """获取所有米哈游游戏（原神/崩铁/绝区零）的最新前瞻直播兑换码。"""
        for game_key in GAMES:
            async for resp in self._handle_code(event, game_key):
                yield resp

    async def terminate(self):
        await self.client.aclose()
