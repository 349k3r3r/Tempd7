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

CATEGORY_ID = 1509993737915338802
TRANSCRIPT_CH = 1509993884355268680
TOS_CH = 1509993970413994054

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
    return json.load(open(name))

def save(name, data):
    json.dump(data, open(name, "w"), indent=4)

vouches = load("vouches.json")
profit = load("profit.json")

TICKETS = {}

# =========================
# HELPERS
# =========================
def is_mm(member):
    return any(r.id in MM_ROLES for r in member.roles)

# =========================
# TICKET DATA
# =========================
def get_ticket(channel_id):
    return TICKETS.get(channel_id)

# =========================
# CLAIM SYSTEM
# =========================
class ClaimView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Claim", style=discord.ButtonStyle.green)
    async def claim(self, interaction: discord.Interaction, button: discord.ui.Button):
        await claim_ticket(interaction)

async def claim_ticket(interaction):
    ch = interaction.channel

    if ch.id not in TICKETS:
        return await interaction.response.send_message("Not a ticket.", ephemeral=True)

    data = TICKETS[ch.id]

    if data.get("claimed"):
        return await interaction.response.send_message("Already claimed.", ephemeral=True)

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

    await interaction.response.send_message(f"Claimed by {interaction.user.mention}")

# =========================
# MODAL
# =========================
class MMModal(discord.ui.Modal, title="Request Middleman"):
    trader = discord.ui.TextInput(label="Who are you trading with?")
    info = discord.ui.TextInput(label="What is the trade info?")

    async def on_submit(self, interaction: discord.Interaction):
        guild = interaction.guild

        ch = await guild.create_text_channel(
            name=f"ticket-{interaction.user.name}",
            category=guild.get_channel(CATEGORY_ID)
        )

        TICKETS[ch.id] = {
            "creator": interaction.user.id,
            "claimed": None,
            "added": []
        }

        embed = discord.Embed(title="MM Ticket")
        embed.add_field(name="Creator", value=interaction.user.mention, inline=False)
        embed.add_field(name="Trader", value=self.trader.value, inline=False)
        embed.add_field(name="Info", value=self.info.value, inline=False)

        await ch.send(embed=embed, view=ClaimView())

        await interaction.response.send_message(f"Created {ch.mention}", ephemeral=True)

# =========================
# PANEL
# =========================
class MMPanel(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Request MM", style=discord.ButtonStyle.blurple)
    async def mm(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(MMModal())

@bot.command()
async def setup(ctx):
    embed = discord.Embed(title="MM Panel")
    embed.description = "Click below to request a middleman."
    await ctx.send(embed=embed, view=MMPanel())

# =========================
# CLOSE BUTTON
# =========================
class CloseView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Close Ticket", style=discord.ButtonStyle.red)
    async def close(self, interaction: discord.Interaction, button: discord.ui.Button):
        await close_ticket(interaction)

async def close_ticket(interaction):
    ch = interaction.channel

    messages = [m async for m in ch.history(limit=200)]
    content = "\n".join([f"{m.author}: {m.content}" for m in messages])

    file = discord.File(io.StringIO(content), filename="transcript.txt")

    log = interaction.guild.get_channel(TRANSCRIPT_CH)

    if log:
        await log.send(file=file)

    # DM transcript
    for uid in TICKETS.get(ch.id, {}).get("added", []):
        m = interaction.guild.get_member(uid)
        if m:
            try:
                await m.send(file=file)
            except:
                pass

    await interaction.response.send_message("Closing in 5 seconds...")
    await asyncio.sleep(5)
    await ch.delete()

# =========================
# ADD / REMOVE USERS
# =========================
@bot.command()
async def add(ctx, user: discord.Member):
    TICKETS[ctx.channel.id]["added"].append(user.id)
    await ctx.channel.set_permissions(user, view_channel=True)
    await ctx.send("Added user.")

@bot.command()
async def remove(ctx, user: discord.Member):
    TICKETS[ctx.channel.id]["added"].remove(user.id)
    await ctx.channel.set_permissions(user, overwrite=None)
    await ctx.send("Removed user.")

# =========================
# CLAIM COMMAND
# =========================
@bot.command()
async def claim(ctx):
    await claim_ticket(ctx)

@bot.command()
async def unclaim(ctx):
    TICKETS[ctx.channel.id]["claimed"] = None
    await ctx.send("Unclaimed.")

# =========================
# VOUCH SYSTEM
# =========================
@bot.command()
async def addvouch(ctx, amt: int):
    vouches[str(ctx.author.id)] = vouches.get(str(ctx.author.id), 0) + amt
    save("vouches.json", vouches)
    await ctx.send("Vouch added.")

@bot.command()
async def removevouch(ctx, amt: int):
    vouches[str(ctx.author.id)] = max(0, vouches.get(str(ctx.author.id), 0) - amt)
    save("vouches.json", vouches)
    await ctx.send("Removed vouch.")

@bot.command()
async def vouches(ctx):
    await ctx.send(vouches.get(str(ctx.author.id), 0))

# =========================
# PROFIT LOGGING
# =========================
@bot.command()
async def log(ctx, profit_amt: int):
    profit[str(ctx.author.id)] = profit.get(str(ctx.author.id), 0) + profit_amt
    save("profit.json", profit)
    await ctx.send("Logged profit.")

@bot.command()
async def altlog(ctx, profit_amt: int):
    await log(ctx, profit_amt)

@bot.command()
async def checkprofit(ctx):
    await ctx.send(profit.get(str(ctx.author.id), 0))

# =========================
# ROLE SYSTEM (simple)
# =========================
@bot.command()
async def role(ctx, user: discord.Member, role: discord.Role):
    if is_mm(ctx.author):
        await user.add_roles(role)
        await ctx.send("Role given.")

# =========================
# TEMP SYSTEM
# =========================
temp = {}

@bot.command()
async def temp(ctx):
    m = ctx.author

    if m.id in temp:
        for r in temp.pop(m.id):
            await m.add_roles(r)
        return await ctx.send("Restored.")

    removed = [r for r in m.roles if r.id in MM_ROLES]
    temp[m.id] = removed

    for r in removed:
        await m.remove_roles(r)

    await m.add_roles(ctx.guild.get_role(MERCY_ROLE))
    await ctx.send("Temp applied.")

# =========================
# MERCY (simple version)
# =========================
@bot.command()
async def mercy(ctx, user: discord.Member):
    embed = discord.Embed(
        title="Mercy System",
        description=f"{user.mention}, you’ve been offered an opportunity.",
        color=0xed4245
    )
    await ctx.send(embed=embed)

# =========================
# TOS
# =========================
@bot.command()
async def tos(ctx):
    embed = discord.Embed(title="TOS")
    embed.description = "Middleman rules apply."
    await ctx.send(embed=embed)

# =========================
# READY
# =========================
@bot.event
async def on_ready():
    print(f"Logged in as {bot.user}")

import os

bot.run(os.getenv("DISCORD_TOKEN"))
