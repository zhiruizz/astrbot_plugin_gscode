---
name: gscode-auto
description: "Automatically invoke AstrBot gscode plugin when the user asks about miHoYo redemption codes. TRIGGER when: user mentions 兑换码, 兑换, 原神兑换码, 崩铁兑换码, 绝区零兑换码, 前瞻直播, redeem code, gscode, hsrcode, zzzcode, or asks about miHoYo game codes. SKIP when: user is discussing code programming, source code, or unrelated topics."
---

# gscode-auto

When the user asks about miHoYo game redemption codes (兑换码), automatically invoke the AstrBot gscode plugin to fetch codes.

## Decision Table

| User Intent | Command |
|---|---|
| Asks for Genshin codes (原神兑换码/原神前瞻) | `/gicode` |
| Asks for Star Rail codes (崩铁兑换码/星铁兑换码/铁道兑换码) | `/hsrcode` |
| Asks for ZZZ codes (绝区零兑换码/ZZZ兑换码) | `/zzzcode` |
| Asks for all codes (兑换码/有没有兑换码) | `/兑换码` |
| Ambiguous (e.g. "帮我查下兑换码") | `/兑换码` |

## Auto-Trigger Rules

1. **Direct ask**: User says "原神兑换码" / "有没有兑换码" / "帮我查兑换码" → invoke the matching command immediately, no confirmation needed
2. **Contextual ask**: User mentions 前瞻直播, 新版本直播, or livestream codes → invoke `/兑换码`
3. **Ambiguous**: User says "兑换码" without specifying game → invoke `/兑换码` (covers all games)
4. **Do NOT trigger**: User mentions 兑换码 in context of discussing plugin code, debugging, or development

## Response Format

After invoking the command, relay the plugin's response directly to the user. Do not add extra commentary unless the plugin returns an error or "暂无资讯".

If the plugin returns codes, present them clearly:

```
🎮 [游戏名] 兑换码

[奖励描述]
[兑换码]

* 兑换码有效期有限，请尽快使用
```

If the plugin returns "暂无前瞻直播资讯", explain:
- 当前没有正在进行的前瞻直播
- 新版本前瞻通常在版本更新前1-2周举行
- 可以稍后再试
