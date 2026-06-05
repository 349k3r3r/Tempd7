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

CATEGORY_ID     = 1509993737915338802
TRANSCRIPT_CH   = 1509993884355268680
TOS_CH          = 1509993970413994054
LOG_CH          = 1509993876742476000   # $log / $altlog channel

MERCY_ROLE = 1509993713596895343

MM_ROLES = [
    1509993712074096780,
    1509993711285567651,
    1509993710446706708,
    1509993709385683117
]

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

TICKETS = {}
temp_store = {}

# =========================
# HELPERS
# =========================
def is_mm(member):
    return any(r.id in MM_ROLES for r in member.roles)

def get_ticket(channel_id):
    return TICKETS.get(channel_id)

# =========================
# CLAIM SYSTEM
# =========================
class ClaimView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Claim", style=discord.ButtonStyle.green, custom_id="claim_btn")
    async def claim(self, interaction: discord.Interaction, button: discord.ui.Button):
        await claim_ticket(interaction)

async def claim_ticket(interaction):
    ch = interaction.channel

    if ch.id not in TICKETS:
        return await interaction.response.send_message("This is not a ticket channel.", ephemeral=True)

    data = TICKETS[ch.id]

    if data.get("claimed"):
        claimer = interaction.guild.get_member(data["claimed"])
        name = claimer.mention if claimer else "someone"
        return await interaction.response.send_message(f"Already claimed by {name}.", ephemeral=True)

    if not is_mm(interaction.user):
        return await interaction.response.send_message("Only middlemen can claim tickets.", ephemeral=True)

    data["claimed"] = interaction.user.id

    overwrites = {
        interaction.guild.default_role: discord.PermissionOverwrite(view_channel=False),
        interaction.guild.get_member(data["creator"]): discord.PermissionOverwrite(view_channel=True),
        interaction.user: discord.PermissionOverwrite(view_channel=True),
    }

    for uid in data.get("added", []):
        m = interaction.guild.get_member(uid)
        if m:
            overwrites[m] = discord.PermissionOverwrite(view_channel=True)

    await ch.edit(overwrites=overwrites)

    embed = discord.Embed(
        description=f"✅ Ticket claimed by {interaction.user.mention}",
        color=0x57f287
    )
    await interaction.response.send_message(embed=embed)

# =========================
# MODAL
# =========================
class MMModal(discord.ui.Modal, title="Request Middleman"):
    trader = discord.ui.TextInput(label="Who are you trading with?", placeholder="Their username or ID")
    info   = discord.ui.TextInput(label="What is the trade info?", style=discord.TextStyle.paragraph, placeholder="Describe the trade details...")

    async def on_submit(self, interaction: discord.Interaction):
        guild = interaction.guild

        ch = await guild.create_text_channel(
            name=f"ticket-{interaction.user.name}",
            category=guild.get_channel(CATEGORY_ID)
        )

        TICKETS[ch.id] = {
            "creator": interaction.user.id,
            "claimed": None,
            "added":   []
        }

        embed = discord.Embed(title="📩 MM Ticket", color=0x5865f2, timestamp=datetime.utcnow())
        embed.add_field(name="Creator",      value=interaction.user.mention, inline=True)
        embed.add_field(name="Trading With", value=self.trader.value,        inline=True)
        embed.add_field(name="Trade Info",   value=self.info.value,          inline=False)
        embed.set_footer(text=f"User ID: {interaction.user.id}")

        view = discord.ui.View(timeout=None)
        view.add_item(discord.ui.Button(label="Claim", style=discord.ButtonStyle.green, custom_id="claim_btn"))

        await ch.send(content="@here A new ticket has been opened!", embed=embed, view=ClaimView())
        await interaction.response.send_message(f"✅ Ticket created: {ch.mention}", ephemeral=True)

# =========================
# PANEL
# =========================
class MMPanel(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Request MM", style=discord.ButtonStyle.blurple, emoji="📩", custom_id="mm_panel_btn")
    async def mm(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(MMModal())

@bot.command()
async def setup(ctx):
    embed = discord.Embed(
        title="Middleman Panel",
        description=(
            "Need a trusted middleman for your trade?\n\n"
            "Click the button below to open a private ticket and a middleman will assist you shortly."
        ),
        color=0x5865f2
    )
    embed.set_footer(text="Only open a ticket if you genuinely need MM services.")
    await ctx.send(embed=embed, view=MMPanel())

# =========================
# CLOSE SYSTEM
# =========================
class CloseView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Close Ticket", style=discord.ButtonStyle.red, emoji="🔒", custom_id="close_btn")
    async def close(self, interaction: discord.Interaction, button: discord.ui.Button):
        await close_ticket(interaction)

async def close_ticket(interaction):
    ch = interaction.channel

    if ch.id not in TICKETS:
        return await interaction.response.send_message("This is not a ticket channel.", ephemeral=True)

    await interaction.response.send_message("🔒 Closing ticket in 5 seconds...")

    messages = [m async for m in ch.history(limit=200, oldest_first=True)]
    lines = []
    for m in messages:
        ts = m.created_at.strftime("%Y-%m-%d %H:%M:%S")
        lines.append(f"[{ts}] {m.author} ({m.author.id}): {m.content}")
    content = "\n".join(lines)

    buf = io.BytesIO(content.encode("utf-8"))
    file1 = discord.File(buf, filename=f"transcript-{ch.name}.txt")

    log_ch = interaction.guild.get_channel(TRANSCRIPT_CH)
    if log_ch:
        embed = discord.Embed(
            title="📋 Ticket Transcript",
            description=f"Ticket: `{ch.name}`\nClosed by: {interaction.user.mention}",
            color=0xfee75c,
            timestamp=datetime.utcnow()
        )
        await log_ch.send(embed=embed, file=file1)

    # DM transcript to added users
    for uid in TICKETS.get(ch.id, {}).get("added", []):
        m = interaction.guild.get_member(uid)
        if m:
            try:
                buf2 = io.BytesIO(content.encode("utf-8"))
                await m.send(
                    f"📋 Transcript for `{ch.name}`",
                    file=discord.File(buf2, filename=f"transcript-{ch.name}.txt")
                )
            except:
                pass

    await asyncio.sleep(5)
    TICKETS.pop(ch.id, None)
    await ch.delete()

@bot.command()
async def close(ctx):
    class FakeInteraction:
        channel = ctx.channel
        guild   = ctx.guild
        user    = ctx.author
        async def response_send(self, *a, **kw): pass
    await close_ticket(ctx)

# =========================
# ADD / REMOVE USERS
# =========================
@bot.command()
async def add(ctx, user: discord.Member):
    if ctx.channel.id not in TICKETS:
        return await ctx.send("This is not a ticket channel.")
    TICKETS[ctx.channel.id]["added"].append(user.id)
    await ctx.channel.set_permissions(user, view_channel=True)
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
    await ctx.send(embed=embed)

@bot.command()
async def unclaim(ctx):
    if ctx.channel.id not in TICKETS:
        return await ctx.send("This is not a ticket channel.")
    TICKETS[ctx.channel.id]["claimed"] = None
    embed = discord.Embed(description="🔓 Ticket has been unclaimed.", color=0xfee75c)
    await ctx.send(embed=embed)

# =========================
# CONFIRM SYSTEM
# =========================
class ConfirmView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=60)
        self.result = None

    @discord.ui.button(label="Confirm ✅", style=discord.ButtonStyle.green)
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.result = True
        await interaction.response.send_message("Trade confirmed.", ephemeral=True)
        self.stop()

    @discord.ui.button(label="Cancel ❌", style=discord.ButtonStyle.red)
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.result = False
        await interaction.response.send_message("Trade cancelled.", ephemeral=True)
        self.stop()

@bot.command()
async def confirm(ctx):
    if ctx.channel.id not in TICKETS:
        return await ctx.send("This is not a ticket channel.")

    view = ConfirmView()
    embed = discord.Embed(
        title="Trade Confirmation",
        description="Please confirm or cancel the trade below.",
        color=0x5865f2
    )
    await ctx.send(embed=embed, view=view)
    await view.wait()

    if view.result is True:
        done = discord.Embed(description="✅ Trade has been marked as **complete**.", color=0x57f287)
        await ctx.send(embed=done)
    elif view.result is False:
        cancelled = discord.Embed(description="❌ Trade has been **cancelled**.", color=0xed4245)
        await ctx.send(embed=cancelled)
    else:
        timed = discord.Embed(description="⏱️ Confirmation timed out.", color=0x99aab5)
        await ctx.send(embed=timed)

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
    embed = discord.Embed(description=f"✅ Added **{amt}** vouch(es) to {user.mention}. Total: **{vouches_data[uid]}**", color=0x57f287)
    await ctx.send(embed=embed)

@bot.command()
async def removevouch(ctx, user: discord.Member, amt: int = 1):
    if not is_mm(ctx.author):
        return await ctx.send("Only middlemen can remove vouches.")
    uid = str(user.id)
    vouches_data[uid] = max(0, vouches_data.get(uid, 0) - amt)
    save("vouches.json", vouches_data)
    embed = discord.Embed(description=f"✅ Removed **{amt}** vouch(es) from {user.mention}. Total: **{vouches_data[uid]}**", color=0xed4245)
    await ctx.send(embed=embed)

@bot.command(name="vouches")
async def check_vouches(ctx, user: discord.Member = None):
    target = user or ctx.author
    uid = str(target.id)
    count = vouches_data.get(uid, 0)
    embed = discord.Embed(
        title="Vouch Count",
        description=f"{target.mention} has **{count}** vouch(es).",
        color=0x5865f2
    )
    await ctx.send(embed=embed)

# =========================
# PROFIT / LOG SYSTEM
# =========================
async def send_log(ctx, mm: discord.Member, hitter: discord.Member, hit_info: str, split: str):
    uid = str(mm.id)
    # Try to parse split as a number and store it
    try:
        split_num = int(split.replace(",", "").replace("$", "").strip())
        profit_data[uid] = profit_data.get(uid, 0) + split_num
        save("profit.json", profit_data)
        total = profit_data[uid]
        total_str = f"{total:,}"
    except ValueError:
        total_str = "N/A"

    log_channel = ctx.guild.get_channel(LOG_CH)
    if not log_channel:
        return await ctx.send("Log channel not found.")

    embed = discord.Embed(
        title="💰 Trade Log",
        color=0x57f287,
        timestamp=datetime.utcnow()
    )
    embed.add_field(name="Middleman",  value=mm.mention,       inline=True)
    embed.add_field(name="Hitter",     value=hitter.mention,   inline=True)
    embed.add_field(name="\u200b",     value="\u200b",          inline=True)
    embed.add_field(name="Hit Info",   value=hit_info,          inline=False)
    embed.add_field(name="Split",      value=split,             inline=True)
    embed.add_field(name="MM Total",   value=total_str,         inline=True)
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
    """Usage: $altlog @mm @hitter <hit info> | <split>  (admin use)"""
    if not is_mm(ctx.author):
        return await ctx.send("Only middlemen can use altlog.")
    if "|" not in rest:
        return await ctx.send("Usage: `$altlog @mm @hitter <hit info> | <split>`")
    hit_info, split = [x.strip() for x in rest.split("|", 1)]
    await send_log(ctx, mm, hitter, hit_info, split)

@bot.command()
async def checkprofit(ctx, user: discord.Member = None):
    target = user or ctx.author
    uid = str(target.id)
    amount = profit_data.get(uid, 0)
    embed = discord.Embed(
        title="Profit",
        description=f"{target.mention} has logged **{amount:,}** in profit.",
        color=0x57f287
    )
    await ctx.send(embed=embed)

# =========================
# ROLE SYSTEM
# =========================
@bot.command()
async def role(ctx, user: discord.Member, *, role: discord.Role):
    if not is_mm(ctx.author):
        return await ctx.send("You don't have permission to give roles.")
    await user.add_roles(role)
    embed = discord.Embed(description=f"✅ Gave {role.mention} to {user.mention}.", color=0x57f287)
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

    embed = discord.Embed(description="✅ MM roles temporarily removed. Run `$temp` again to restore.", color=0xfee75c)
    await ctx.send(embed=embed)

# =========================
# MERCY SYSTEM
# =========================
@bot.command()
async def mercy(ctx, user: discord.Member):
    embed = discord.Embed(
        title="⚠️ Mercy Offer",
        description=(
            f"{user.mention}, you have been offered **mercy**.\n\n"
            f"Respond within **5 minutes** or the offer expires."
        ),
        color=0xed4245,
        timestamp=datetime.utcnow()
    )
    embed.set_footer(text=f"Offered by {ctx.author}")
    await ctx.send(embed=embed)

    def check(m):
        return m.author.id == user.id and m.channel == ctx.channel

    try:
        response = await bot.wait_for("message", timeout=300, check=check)
        reply = discord.Embed(
            description=f"✅ {user.mention} responded to the mercy offer.",
            color=0x57f287
        )
        await ctx.send(embed=reply)
    except asyncio.TimeoutError:
        expired = discord.Embed(
            description=f"⏱️ {user.mention} did not respond. Mercy offer has expired.",
            color=0x99aab5
        )
        await ctx.send(embed=expired)

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
# TOS
# =========================
@bot.command()
async def tos(ctx):
    ch = ctx.guild.get_channel(TOS_CH)
    ref = ch.mention if ch else "the TOS channel"
    embed = discord.Embed(
        title="📜 Terms of Service",
        description=(
            f"By using our middleman service you agree to all rules.\n\n"
            f"Please read our full TOS in {ref}."
        ),
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

bot.run(os.getenv("DISCORD_TOKEN"))
