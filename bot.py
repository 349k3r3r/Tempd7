import discord
from discord import app_commands
from discord.ext import commands
import json
import asyncio
import os
import io
from datetime import datetime

# =========================
# BOT SETUP
# =========================
intents = discord.Intents.all()
bot = commands.Bot(command_prefix="!", intents=intents)
GUILD_ID = 1509986055112233042
GUILD    = discord.Object(id=GUILD_ID)

# =========================
# CONFIG
# =========================
CATEGORY_ID   = 1509993737915338802
TRANSCRIPT_CH = 1509993884355268680
TOS_CH        = 1509993970413994054

MERCY_ROLE  = 1509993713596895343
HITTER_ROLE = 1509993713596895343   # role given on mercy accept

BAN_ROLE_ID = 1512530606884520108   # only role that can use /manageban

MM_ROLES = [
    1509993712074096780,
    1509993711285567651,
    1509993710446706708,
    1509993709385683117,
]

# Hierarchy lowest → highest
HIERARCHY = [
    1509993709385683117,  # Middleman
    1509993710446706708,  # Head MM
    1509993711285567651,  # Lead MM
    1509993712074096780,  # MM Manager
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

TICKETS    = {}
temp_store = {}

# =========================
# HELPERS
# =========================
def is_mm(member: discord.Member) -> bool:
    return any(r.id in MM_ROLES for r in member.roles)

def has_role(member: discord.Member, role_ids: list) -> bool:
    return any(r.id in role_ids for r in member.roles)

def top_hierarchy_idx(member: discord.Member) -> int:
    idx = -1
    for i, rid in enumerate(HIERARCHY):
        if any(r.id == rid for r in member.roles):
            idx = i
    return idx

MM_PING_ROLE = 1509993709385683117  # Only the base Middleman role gets pinged on new tickets

def mm_ping_str(guild: discord.Guild) -> str:
    r = guild.get_role(MM_PING_ROLE)
    return r.mention if r else ""

def ts_now() -> str:
    return discord.utils.utcnow().strftime("%A, %B %d, %Y %I:%M %p")

def time_short() -> str:
    return discord.utils.utcnow().strftime("%I:%M %p")

async def make_transcript(channel: discord.TextChannel) -> io.BytesIO:
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
# MERCY SYSTEM
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
            try:
                await interaction.user.add_roles(role)
            except discord.Forbidden:
                pass  # Bot role is below hitter role in server hierarchy — fix in Server Settings > Roles

        embed = discord.Embed(
            title="✅ Opportunity Accepted",
            description=f"{interaction.user.mention} has accepted the opportunity and has been verified.",
            color=0x57f287
        )
        embed.set_footer(text=f"{FOOTER} • Today at {time_short()}")

        for child in self.children:
            child.disabled = True
            if child.label == "Accept":
                child.label = "Accepted"

        await interaction.response.edit_message(embed=embed, view=self)

        dm_embed = discord.Embed(title="💫 Hitting Tutorial", color=0x2b2d31)
        dm_embed.description = (
            "You're a hitter now. A hitter is someone that got scammed by us, "
            "and goes out to scam others. In other words, you're now a scammer."
        )
        dm_embed.add_field(
            name="❓ What should I do?",
            value=(
                "You need to go and advertise trades on other servers. "
                "Once the other trader/victim DMs you, lead the conversation towards using a middleman. "
                f"Once they agree, send them our server and create a ticket in <#{CATEGORY_ID}>. "
                "A random middleman will come assist you."
            ), inline=False)
        dm_embed.add_field(
            name="💰 How do I get profit?",
            value="After you hit/scam for an item, you and the Middleman will split the item 50/50.",
            inline=False)
        dm_embed.add_field(
            name="🤔 Can I become a middleman?",
            value="Absolutely, but it does not come free. Check the requirements channel to rank up.",
            inline=False)
        dm_embed.add_field(
            name="📊 Keep in mind",
            value="Hits need to be posted in the hits channel or they will not count.",
            inline=False)
        dm_embed.add_field(
            name="📖 Any guide for hitting?",
            value="We have a tutorial channel to help with hitting.",
            inline=False)
        dm_embed.add_field(
            name="ℹ️ Other info?",
            value="Check the rules channel to make sure you're not breaking any rules.",
            inline=False)
        dm_embed.set_footer(text=FOOTER)

        try:
            await interaction.user.send(embed=dm_embed)
        except discord.Forbidden:
            pass

        ghost_ch = interaction.guild.get_channel(CATEGORY_ID)
        if ghost_ch:
            ghost_msg = await ghost_ch.send(interaction.user.mention)
            await ghost_msg.delete()

    @discord.ui.button(label="Decline", style=discord.ButtonStyle.danger, custom_id="v:mercy_decline")
    async def decline(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.target and interaction.user.id != self.target.id:
            return await interaction.response.send_message(
                "❌ Only the targeted user can respond.", ephemeral=True)

        embed = discord.Embed(
            title="❌ Opportunity Declined",
            description=f"{interaction.user.mention} has declined the opportunity.",
            color=0xed4245
        )
        embed.set_footer(text=f"{FOOTER} • Today at {time_short()}")

        for child in self.children:
            child.disabled = True
            if child.label == "Decline":
                child.label = "Declined"

        await interaction.response.edit_message(embed=embed, view=self)


@bot.tree.command(name="mercy", description="Send a mercy offer to a user", guild=GUILD)
@app_commands.describe(user="User to send mercy to")
async def slash_mercy(interaction: discord.Interaction, user: discord.Member):
    if not is_mm(interaction.user):
        return await interaction.response.send_message("❌ No permission.", ephemeral=True)

    await interaction.response.defer(ephemeral=True)
    now = time_short()

    scam_embed = discord.Embed(
        title="⚠️ Scam Notification",
        description=(
            "If you're seeing this, you've likely just been scammed — but this doesn't end how you think.\n\n"
            "Most people in this server started out the same way. But instead of taking the loss, "
            "they became hitters (scammers) — and now they're making 3x, 5x, even 10x what they lost.\n\n"
            "This is your chance to turn a setback into serious profit.\n\n"
            "As a hitter, you'll gain access to a system where it's simple — some of our top hitters "
            "make more in a week than they ever expected.\n\n"
            "You now have access to the staff chat and other hitter channels. "
            "Head to the main guide channel to learn how to start.\n\n"
            "🔥 Every minute you wait is profit missed.\n\n"
            "Need help getting started? Ask in the support system channel.\n\n"
            "You've already been pulled in — now it's time to flip the script and come out ahead."
        ),
        color=0xed4245
    )
    scam_embed.set_footer(text=f"{FOOTER} • Today at {now}")

    offer_embed = discord.Embed(
        description=(
            f"{user.mention}, do you want to accept this opportunity and become a hitter?\n\n"
            "⏳ **You have 1 minute to respond. The decision is yours. Make it count.**"
        ),
        color=0xed4245
    )
    offer_embed.set_footer(text=f"{FOOTER} • Today at {now}")

    view = MercyView(target=user, author=interaction.user)
    await interaction.channel.send(content=user.mention, embed=scam_embed)
    await interaction.channel.send(embed=offer_embed, view=view)
    await interaction.followup.send("✅ Mercy sent.", ephemeral=True)


# =========================
# TICKET SYSTEM
# =========================
class ClaimView(discord.ui.View):
    def __init__(self, creator_id=None):
        super().__init__(timeout=None)
        self.creator_id = creator_id

    @discord.ui.button(label="Claim", style=discord.ButtonStyle.success, custom_id="v:claim_btn")
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

        button.disabled = True
        button.label = "Claimed"
        await interaction.message.edit(view=self)

        claimed_embed = discord.Embed(
            title="✅ Ticket Claimed",
            description=f"{interaction.user.mention} will be your Middleman for today.",
            color=0x57f287
        )
        claimed_embed.set_footer(text=f"{FOOTER} • Today at {time_short()}")

        await interaction.response.defer()
        await ch.send(embed=claimed_embed, view=CloseView())




class CloseView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Close", style=discord.ButtonStyle.danger, emoji="🔒", custom_id="v:close_btn")
    async def close(self, interaction: discord.Interaction, button: discord.ui.Button):
        await do_close(interaction)


async def do_close(interaction: discord.Interaction):
    ch    = interaction.channel
    guild = interaction.guild

    if ch.id not in TICKETS:
        return await interaction.response.send_message("This is not a ticket channel.", ephemeral=True)

    data = TICKETS[ch.id]
    buf  = await make_transcript(ch)

    tr_ch = guild.get_channel(TRANSCRIPT_CH)
    if tr_ch:
        embed = discord.Embed(
            title=f"📋 Transcript — {ch.name}",
            color=0xfee75c,
            timestamp=discord.utils.utcnow()
        )
        creator = guild.get_member(data.get("creator"))
        claimer = guild.get_member(data.get("claimed")) if data.get("claimed") else None
        embed.add_field(name="Ticket Creator", value=creator.mention if creator else "Unknown", inline=True)
        embed.add_field(name="Claimed By",     value=claimer.mention if claimer else "Unclaimed", inline=True)
        embed.add_field(name="Closed By",      value=interaction.user.mention, inline=True)
        embed.set_footer(text=FOOTER)
        await tr_ch.send(embed=embed, file=discord.File(buf, filename=f"transcript-{ch.name}.txt"))

    await interaction.response.send_message("🔒 Closing ticket in 5 seconds...")
    await asyncio.sleep(5)
    TICKETS.pop(ch.id, None)
    await ch.delete()


class MMModal(discord.ui.Modal, title="Request Middleman"):
    trader = discord.ui.TextInput(
        label="Who are you trading with?",
        placeholder="Their username or @mention",
        required=True
    )
    info = discord.ui.TextInput(
        label="What is the trade?",
        style=discord.TextStyle.paragraph,
        placeholder="Describe what items/currency are being traded...",
        required=True
    )

    async def on_submit(self, interaction: discord.Interaction):
        guild = interaction.guild
        ch    = await guild.create_text_channel(
            name=f"ticket-{interaction.user.name}",
            category=guild.get_channel(CATEGORY_ID),
            topic=str(interaction.user.id)
        )
        TICKETS[ch.id] = {"creator": interaction.user.id, "claimed": None, "added": []}

        embed = discord.Embed(title="🎫 Middleman Ticket", color=0x2b2d31)
        embed.description = (
            f"{interaction.user.mention}, thank you for using our middleman services.\n\n"
            "Please wait for a middleman to assist you.\n\n"
            "If you have any questions, please let a staff member know."
        )
        embed.set_footer(text=f"{FOOTER} • Today at {time_short()}")

        ping = mm_ping_str(guild) + f" {interaction.user.mention}"
        await ch.send(content=ping, embed=embed, view=ClaimView(creator_id=interaction.user.id))
        await interaction.response.send_message(f"✅ Ticket created: {ch.mention}", ephemeral=True)


class MMPanel(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Request Middleman", style=discord.ButtonStyle.primary,
                       emoji="🎫", custom_id="v:mm_panel_btn")
    async def mm(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(MMModal())


@bot.tree.command(name="setup", description="Post the MM request panel", guild=GUILD)
async def slash_setup(interaction: discord.Interaction):
    if not is_mm(interaction.user):
        return await interaction.response.send_message("❌ No permission.", ephemeral=True)
    embed = discord.Embed(title="🛡️ Middleman Services", color=0x2b2d31)
    embed.add_field(
        name="Middleman Service",
        value="To request a middleman, click the **Request Middleman** button below.",
        inline=False)
    embed.add_field(
        name="How does middleman work?",
        value=(
            "• Trader #1 gives their item to the middleman.\n"
            "• Trader #2 gives their item to the middleman.\n"
            "• Middleman gives each trader their respective item."
        ),
        inline=False)
    embed.add_field(
        name="⚠️ DISCLAIMER",
        value="You must both agree on the deal before using a middleman. Troll tickets will have consequences.",
        inline=False)
    embed.set_footer(text=f"{FOOTER} • Today at {time_short()}")
    await interaction.channel.send(embed=embed, view=MMPanel())
    await interaction.response.send_message("✅ Panel deployed.", ephemeral=True)


@bot.tree.command(name="close", description="Close this ticket", guild=GUILD)
async def slash_close(interaction: discord.Interaction):
    await do_close(interaction)


@bot.tree.command(name="add", description="Add a user to this ticket", guild=GUILD)
@app_commands.describe(user="User to add")
async def slash_add(interaction: discord.Interaction, user: discord.Member):
    if not is_mm(interaction.user):
        return await interaction.response.send_message("❌ No permission.", ephemeral=True)
    ch = interaction.channel
    if ch.id not in TICKETS:
        return await interaction.response.send_message("This is not a ticket channel.", ephemeral=True)
    TICKETS[ch.id]["added"].append(user.id)
    await ch.set_permissions(user, view_channel=True, send_messages=True)
    embed = discord.Embed(
        description=f"✅ {user.mention} has been added to the ticket by {interaction.user.mention}.",
        color=0x57f287
    )
    embed.set_footer(text=f"{FOOTER} • Today at {time_short()}")
    await interaction.response.send_message(embed=embed)


@bot.tree.command(name="remove", description="Remove a user from this ticket", guild=GUILD)
@app_commands.describe(user="User to remove")
async def slash_remove(interaction: discord.Interaction, user: discord.Member):
    if not is_mm(interaction.user):
        return await interaction.response.send_message("❌ No permission.", ephemeral=True)
    ch = interaction.channel
    if ch.id not in TICKETS:
        return await interaction.response.send_message("This is not a ticket channel.", ephemeral=True)
    if user.id in TICKETS[ch.id]["added"]:
        TICKETS[ch.id]["added"].remove(user.id)
    await ch.set_permissions(user, overwrite=None)
    embed = discord.Embed(
        description=f"❌ {user.mention} has been removed from the ticket by {interaction.user.mention}.",
        color=0xed4245
    )
    embed.set_footer(text=f"{FOOTER} • Today at {time_short()}")
    await interaction.response.send_message(embed=embed)


# =========================
# TRADE CONFIRM
# =========================
class TradeView(discord.ui.View):
    def __init__(self, t1: int, t2: int, mm: int):
        super().__init__(timeout=None)
        self.t1 = t1
        self.t2 = t2
        self.mm = mm
        self.confirmed: set = set()

        b1 = discord.ui.Button(label="✅ Confirm Trade (Trader 1)", style=discord.ButtonStyle.success,
                                custom_id=f"trade_t1_{t1}_{t2}")
        b2 = discord.ui.Button(label="✅ Confirm Trade (Trader 2)", style=discord.ButtonStyle.success,
                                custom_id=f"trade_t2_{t1}_{t2}")
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
        old     = interaction.message.embeds[0]
        details = old.fields[0].value if old.fields else "—"

        if t1c and t2c:
            embed = discord.Embed(color=0x57f287, title="✅ Trade Confirmed")
            embed.description = "Both traders have confirmed. Please proceed with the trade."
            embed.add_field(name="🔵 Trader 1",  value=m1.mention if m1 else str(self.t1), inline=True)
            embed.add_field(name="🔵 Trader 2",  value=m2.mention if m2 else str(self.t2), inline=True)
            embed.add_field(name="🛡️ Middleman", value=mm.mention if mm else str(self.mm), inline=False)
            embed.add_field(name="✅ Status",     value="Both traders confirmed", inline=False)
            embed.set_footer(text=FOOTER)
            for item in self.children:
                item.disabled = True
                item.label = "Trade Confirmed"
        else:
            t1d = "🟢" if t1c else "🔴"
            t2d = "🟢" if t2c else "🔴"
            embed = discord.Embed(color=0x2b2d31, title="✅ Trade Confirmation")
            embed.description = "Both traders need to confirm to continue."
            embed.add_field(name="📊 Trade Information", value=details, inline=False)
            embed.add_field(name="🔵 Trader 1",  value=m1.mention if m1 else str(self.t1), inline=True)
            embed.add_field(name="🔵 Trader 2",  value=m2.mention if m2 else str(self.t2), inline=True)
            embed.add_field(name="🛡️ Middleman", value=mm.mention if mm else str(self.mm), inline=False)
            embed.add_field(
                name="⏳ Awaiting Confirmation",
                value=f"{t1d} {m1.mention if m1 else str(self.t1)}\n{t2d} {m2.mention if m2 else str(self.t2)}",
                inline=False)
            embed.set_footer(text=FOOTER)
            for item in self.children:
                if "t1" in item.custom_id and t1c:
                    item.label, item.disabled = "Confirmed (Trader 1)", True
                if "t2" in item.custom_id and t2c:
                    item.label, item.disabled = "Confirmed (Trader 2)", True

        await interaction.message.edit(embed=embed, view=self)
        await interaction.response.defer()


@bot.tree.command(name="confirm", description="Start a trade confirmation", guild=GUILD)
@app_commands.describe(trader1="First trader", trader2="Second trader", details="Trade details")
async def slash_confirm(interaction: discord.Interaction,
                        trader1: discord.Member, trader2: discord.Member, details: str):
    if not is_mm(interaction.user):
        return await interaction.response.send_message("❌ No permission.", ephemeral=True)

    view  = TradeView(t1=trader1.id, t2=trader2.id, mm=interaction.user.id)
    embed = discord.Embed(color=0x2b2d31, title="✅ Trade Confirmation")
    embed.description = "Both traders need to confirm to continue."
    embed.add_field(name="📊 Trade Information", value=details,                  inline=False)
    embed.add_field(name="🔵 Trader 1",          value=trader1.mention,          inline=True)
    embed.add_field(name="🔵 Trader 2",          value=trader2.mention,          inline=True)
    embed.add_field(name="🛡️ Middleman",         value=interaction.user.mention, inline=False)
    embed.add_field(name="⏳ Awaiting Confirmation",
                    value=f"🔴 {trader1.mention}\n🔴 {trader2.mention}",         inline=False)
    embed.set_footer(text=FOOTER)
    await interaction.response.send_message(
        content=f"{trader1.mention} {trader2.mention}", embed=embed, view=view)


# =========================
# VOUCH SYSTEM
# =========================
@bot.tree.command(name="addvouch", description="Add vouches to a user", guild=GUILD)
@app_commands.describe(user="Target user", amount="Number of vouches to add")
async def slash_addvouch(interaction: discord.Interaction, user: discord.Member, amount: int = 1):
    if not is_mm(interaction.user):
        return await interaction.response.send_message("❌ No permission.", ephemeral=True)
    uid = str(user.id)
    vouches_data[uid] = vouches_data.get(uid, 0) + amount
    save("vouches.json", vouches_data)
    embed = discord.Embed(
        description=f"✅ Added **{amount}** vouch(es) to {user.mention}. Total: **{vouches_data[uid]}**",
        color=0x57f287
    )
    embed.set_footer(text=f"{FOOTER} • Today at {time_short()}")
    await interaction.response.send_message(embed=embed)


@bot.tree.command(name="removevouch", description="Remove vouches from a user", guild=GUILD)
@app_commands.describe(user="Target user", amount="Number of vouches to remove")
async def slash_removevouch(interaction: discord.Interaction, user: discord.Member, amount: int = 1):
    if not is_mm(interaction.user):
        return await interaction.response.send_message("❌ No permission.", ephemeral=True)
    uid = str(user.id)
    vouches_data[uid] = max(0, vouches_data.get(uid, 0) - amount)
    save("vouches.json", vouches_data)
    embed = discord.Embed(
        description=f"✅ Removed **{amount}** vouch(es) from {user.mention}. Total: **{vouches_data[uid]}**",
        color=0xed4245
    )
    embed.set_footer(text=f"{FOOTER} • Today at {time_short()}")
    await interaction.response.send_message(embed=embed)


@bot.tree.command(name="vouches", description="Check a user's vouch count", guild=GUILD)
@app_commands.describe(user="User to check (leave blank for yourself)")
async def slash_vouches(interaction: discord.Interaction, user: discord.Member = None):
    target = user or interaction.user
    uid    = str(target.id)
    count  = vouches_data.get(uid, 0)
    embed  = discord.Embed(
        title=f"Vouches — {target.display_name}",
        description=f"{target.mention} has **{count}** vouch(es).",
        color=0x5865f2
    )
    embed.set_footer(text=f"{FOOTER} • Today at {time_short()}")
    await interaction.response.send_message(embed=embed)


# =========================
# TRANSFER TICKET
# =========================
@bot.tree.command(name="transfer", description="Transfer this ticket to another middleman", guild=GUILD)
@app_commands.describe(user="Middleman to transfer the ticket to")
async def slash_transfer(interaction: discord.Interaction, user: discord.Member):
    if not is_mm(interaction.user):
        return await interaction.response.send_message("❌ No permission.", ephemeral=True)
    ch = interaction.channel
    if ch.id not in TICKETS:
        return await interaction.response.send_message("This is not a ticket channel.", ephemeral=True)

    # Give new MM full access, remove send from the one transferring
    await ch.set_permissions(user, view_channel=True, send_messages=True)
    await ch.set_permissions(interaction.user, view_channel=True, send_messages=False)

    # Update claimed
    TICKETS[ch.id]["claimed"] = user.id

    embed = discord.Embed(title="🔄 Ticket Transferred", color=0x2b2d31)
    embed.add_field(name="Transferred From", value=interaction.user.mention, inline=True)
    embed.add_field(name="Transferred To",   value=user.mention,             inline=True)
    embed.set_footer(text=f"{FOOTER} • Today at {time_short()}")
    await interaction.response.send_message(content=user.mention, embed=embed)


# =========================
# TEMP SYSTEM
# =========================
@bot.tree.command(name="temp", description="Toggle your MM roles on/off temporarily", guild=GUILD)
async def slash_temp(interaction: discord.Interaction):
    member = interaction.user
    if member.id in temp_store:
        for r in temp_store.pop(member.id):
            try:
                await member.add_roles(r)
            except:
                pass
        embed = discord.Embed(description="✅ MM roles restored.", color=0x57f287)
        embed.set_footer(text=f"{FOOTER} • Today at {time_short()}")
        return await interaction.response.send_message(embed=embed, ephemeral=True)

    removed = [r for r in member.roles if r.id in MM_ROLES]
    if not removed:
        return await interaction.response.send_message("You have no MM roles to remove.", ephemeral=True)

    temp_store[member.id] = removed
    for r in removed:
        try:
            await member.remove_roles(r)
        except:
            pass
    mercy_role = interaction.guild.get_role(MERCY_ROLE)
    if mercy_role:
        await member.add_roles(mercy_role)

    embed = discord.Embed(
        description="✅ MM roles temporarily removed. Run `/temp` again to restore.",
        color=0xfee75c
    )
    embed.set_footer(text=f"{FOOTER} • Today at {time_short()}")
    await interaction.response.send_message(embed=embed, ephemeral=True)


# =========================
# MANAGE ROLE  (screenshot style)
# =========================
@bot.tree.command(name="managerole", description="Give or remove a role from a user", guild=GUILD)
@app_commands.describe(
    action="add or remove",
    user="Target user",
    role="Role to manage",
    reason="Reason"
)
@app_commands.choices(action=[
    app_commands.Choice(name="add",    value="add"),
    app_commands.Choice(name="remove", value="remove"),
])
async def slash_managerole(interaction: discord.Interaction,
                            action: str,
                            user: discord.Member,
                            role: discord.Role,
                            reason: str):
    executor_idx = top_hierarchy_idx(interaction.user)
    if executor_idx == -1:
        return await interaction.response.send_message("❌ No permission.", ephemeral=True)

    # Can only manage roles below their own level
    try:
        target_idx = HIERARCHY.index(role.id)
    except ValueError:
        # Role not in hierarchy — only top rank can assign non-hierarchy roles
        if executor_idx < len(HIERARCHY) - 1:
            return await interaction.response.send_message(
                "❌ You can only manage roles within the hierarchy.", ephemeral=True)
        target_idx = 0  # allow

    if target_idx >= executor_idx:
        return await interaction.response.send_message(
            "❌ You can only manage roles below your own rank.", ephemeral=True)

    if action == "add":
        await user.add_roles(role, reason=reason)
        title, color = "Role Given ✅", 0x57f287
    else:
        await user.remove_roles(role, reason=reason)
        title, color = "Role Removed ❌", 0xed4245

    embed = discord.Embed(title=title, color=color)
    embed.add_field(name="Actioned By", value=f"{interaction.user} ({interaction.user.id})", inline=False)
    embed.add_field(name="Target User", value=f"{user} ({user.id})",                         inline=False)
    embed.add_field(name="Role",        value=role.name,                                      inline=False)
    embed.add_field(name="Reason",      value=reason,                                         inline=False)
    embed.add_field(name="Time",        value=ts_now(),                                       inline=False)
    embed.set_footer(text=f"{FOOTER} • Today at {time_short()}")
    await interaction.response.send_message(embed=embed)


# =========================
# MANAGE BAN  (screenshot style)
# =========================
@bot.tree.command(name="manageban", description="Ban or unban a user", guild=GUILD)
@app_commands.describe(
    action="ban or unban",
    user="Target user",
    reason="Reason for the action"
)
@app_commands.choices(action=[
    app_commands.Choice(name="ban",   value="ban"),
    app_commands.Choice(name="unban", value="unban"),
])
async def slash_manageban(interaction: discord.Interaction,
                           action: str,
                           user: discord.Member,
                           reason: str):
    if not has_role(interaction.user, [BAN_ROLE_ID]):
        return await interaction.response.send_message("❌ No permission.", ephemeral=True)

    roles_owned = [r.name for r in user.roles if r.name != "@everyone"]

    if action == "ban":
        await user.ban(reason=reason, delete_message_days=0)
        title, color = "User Banned 🚫", 0xed4245
    else:
        await interaction.guild.unban(discord.Object(id=user.id), reason=reason)
        title, color = "User Unbanned ✅", 0x57f287

    embed = discord.Embed(title=title, color=color)
    embed.add_field(name="Actioned By",  value=f"{interaction.user} ({interaction.user.id})", inline=False)
    embed.add_field(name="Target User",  value=f"{user} ({user.id})",                          inline=False)
    embed.add_field(name="Roles Owned",  value=", ".join(roles_owned) if roles_owned else "None", inline=False)
    embed.add_field(name="Reason",       value=reason,                                          inline=False)
    embed.add_field(name="Time",         value=ts_now(),                                        inline=False)
    embed.set_footer(text=f"{FOOTER} • Today at {time_short()}")
    await interaction.response.send_message(embed=embed)


# =========================
# TOS
# =========================
@bot.tree.command(name="tos", description="Post the Middleman Terms of Service", guild=GUILD)
async def slash_tos(interaction: discord.Interaction):
    if not is_mm(interaction.user):
        return await interaction.response.send_message("❌ No permission.", ephemeral=True)

    embed = discord.Embed(
        title="📋 Middleman Terms of Service",
        color=0x2b2d31
    )
    embed.add_field(
        name="1. 🚫 No Refunds Once Confirmed",
        value="Once trade is confirmed, it is final.",
        inline=False
    )
    embed.add_field(
        name="2. 🐻 Proof May Be Required",
        value="Valid screenshots or videos may be requested.",
        inline=False
    )
    embed.add_field(
        name="3. 🎭 No Illegal Items",
        value="No stolen accounts, NSFW, or illegal goods.",
        inline=False
    )
    embed.add_field(
        name="4. ⏰ Be Ready",
        value="Both parties must be ready or trade may be canceled.",
        inline=False
    )
    embed.add_field(
        name="5. 🛡️ Scams and Disputes",
        value="Report to | support-system.",
        inline=False
    )
    embed.add_field(
        name="6. 💰 Fees",
        value="Middleman service is 5% of trade value.",
        inline=False
    )
    embed.add_field(
        name="7. ✅ Agreement",
        value="Using this service means you agree to these terms.",
        inline=False
    )
    embed.set_footer(text=f"{FOOTER} • Today at {time_short()}")
    await interaction.channel.send(embed=embed)
    await interaction.response.send_message("✅ TOS posted.", ephemeral=True)


# =========================
# ON READY
# =========================
@bot.event
async def on_ready():
    print(f"✅ Logged in as {bot.user} ({bot.user.id})")
    bot.add_view(ClaimView())
    bot.add_view(CloseView())
    bot.add_view(MMPanel())
    bot.add_view(MercyView())
    bot.tree.copy_global_to(guild=GUILD)
    synced = await bot.tree.sync(guild=GUILD)
    print(f"✅ Synced {len(synced)} slash commands to guild {GUILD_ID}")


bot.run(os.getenv("DISCORD_TOKEN"))
