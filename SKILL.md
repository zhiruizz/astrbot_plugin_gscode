---
name: gscode-auto
description: "Automatically invoke AstrBot gscode plugin when the user asks about miHoYo redemption codes. TRIGGER when: user mentions 兑换码, 兑换, 原神兑换码, 崩铁兑换码, 绝区零兑换码, 前瞻直播, redeem code, gscode, hsrcode, zzzcode, or asks about miHoYo game codes. SKIP when: user is discussing code programming, source code, or unrelated topics."
---

# gscode-auto

When the user asks about miHoYo game redemption codes (兑换码), use the registered LLM tools to fetch codes automatically.

## Available LLM Tools

The plugin registers these tools that you can call directly:

| Tool Name | When to Call |
|---|---|
| `get_genshin_code` | User asks about 原神/原神兑换码 |
| `get_hsr_code` | User asks about 崩铁/星铁/星穹铁道兑换码 |
| `get_zzz_code` | User asks about 绝区零/ZZZ兑换码 |
| `get_all_codes` | User asks generically about 兑换码, or mentions multiple games |

## Decision Rules

1. **Specific game mentioned** → call the matching tool
2. **Generic "兑换码"** → call `get_all_codes`
3. **"有没有兑换码" / "帮我查兑换码"** → call `get_all_codes`
4. **Do NOT trigger** when user mentions 兑换码 in context of plugin development/debugging

## Response Format

After calling the tool, relay the result directly. Do not add extra commentary unless the tool returns an error or "暂无资讯".

If codes are returned:
```
🎮 [游戏名] 兑换码查询结果
来源：[来源]

[奖励描述]
[兑换码]

* 兑换码有效期有限，请尽快使用
```

If "暂无前瞻直播资讯":
```
当前没有正在进行的前瞻直播。
新版本前瞻通常在版本更新前1-2周举行，届时再查询即可。
```
