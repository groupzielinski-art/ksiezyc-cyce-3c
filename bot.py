import os
import sqlite3
import discord
from discord.ext import commands, tasks
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

TZ = ZoneInfo("Europe/Warsaw")
TOKEN = os.environ["DISCORD_TOKEN"]

TASKS = [
    ("🍽️ Załaduj zmywarkę", 1),
    ("🍴 Opróżnij zmywarkę", 1),
    ("🗑️ Wynieś śmieci", 1),
    ("🐕 Nakarm psy", 1),
    ("🐾 Wyprowadź psy", 2),
    ("🐟 Nakarm rybki", 1),
    ("🧹 Odkurzanie", 2),
    ("🧽 Mycie podłóg", 3),
    ("👕 Zrób pranie", 2),
    ("🍳 Posprzątaj kuchnię", 3),
    ("🚿 Posprzątaj łazienkę", 4)
]

db = sqlite3.connect(
    os.getenv("DB_PATH", "dom.db")
)

db.execute("""
CREATE TABLE IF NOT EXISTS points (
    id INTEGER PRIMARY KEY,
    guild INTEGER,
    user INTEGER,
    task TEXT,
    score INTEGER,
    day TEXT
)
""")

db.execute("""
CREATE TABLE IF NOT EXISTS boards (
    guild INTEGER PRIMARY KEY,
    channel INTEGER,
    message INTEGER,
    day TEXT
)
""")
db.commit()

def today():
    return datetime.now(TZ).date().isoformat()

def board(guild):
    e = discord.Embed(
        title="🌙 KSIĘŻYC CYCE 3C",
        description=(
            "📅 " + today() +
            "\nKliknij po wykonaniu zadania."
            "\nKażde wykonanie daje punkty!"
        ),
        color=0x5865F2
    )
    for name, score in TASKS:
        count = db.execute(
            """SELECT COUNT(*) FROM points
            WHERE guild=? AND task=? AND day=?""",
            (guild, name, today())
        ).fetchone()[0]
        e.add_field(
            name=name,
            value=f"⭐ {score} pkt | Wykonano: {count}",
            inline=False
        )
    return e

class TaskButton(discord.ui.Button):
    def __init__(self, index):
        self.index = index
        name, score = TASKS[index]
        super().__init__(
            label=f"{name} +{score}",
            style=discord.ButtonStyle.success,
            custom_id=f"task_{index}"
        )

    async def callback(self, interaction):
        name, score = TASKS[self.index]
        guild = interaction.guild_id
        db.execute(
            """INSERT INTO points
            (guild,user,task,score,day)
            VALUES (?,?,?,?,?)""",
            (guild, interaction.user.id,
             name, score, today())
        )
        db.commit()
        await interaction.response.edit_message(
            embed=board(guild)
        )
        await interaction.followup.send(
            f"✅ {interaction.user.mention}"
            f" otrzymuje {score} pkt!",
            ephemeral=True
        )

class BoardView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)
        for i in range(len(TASKS)):
            self.add_item(TaskButton(i))

class HomeBot(commands.Bot):
    async def setup_hook(self):
        self.add_view(BoardView())
        await self.tree.sync()
        refresh.start()

bot = HomeBot(
    command_prefix="!",
    intents=discord.Intents.default()
)

@bot.tree.command(
    name="tablica",
    description="Utwórz tablicę obowiązków"
)
@discord.app_commands.guild_only()
@discord.app_commands.default_permissions(
    manage_guild=True
)
async def tablica(interaction):
    await interaction.response.send_message(
        embed=board(interaction.guild_id),
        view=BoardView()
    )
    msg = await interaction.original_response()
    db.execute(
        "REPLACE INTO boards VALUES (?,?,?,?)",
        (interaction.guild_id,
         interaction.channel_id,
         msg.id, today())
    )
    db.commit()

@bot.tree.command(
    name="ranking",
    description="Ranking punktów domowników"
)
@discord.app_commands.guild_only()
@discord.app_commands.choices(okres=[
    discord.app_commands.Choice(
        name="Dzisiaj", value="day"),
    discord.app_commands.Choice(
        name="Tydzień", value="week"),
    discord.app_commands.Choice(
        name="Miesiąc", value="month")
])
async def ranking(
    interaction,
    okres: discord.app_commands.Choice[str]
):
    d = datetime.now(TZ).date()
    if okres.value == "week":
        d -= timedelta(days=d.weekday())
    elif okres.value == "month":
        d = d.replace(day=1)

    rows = db.execute(
        """SELECT user,SUM(score) FROM points
        WHERE guild=? AND day>=?
        GROUP BY user ORDER BY SUM(score) DESC""",
        (interaction.guild_id, d.isoformat())
    ).fetchall()

    result = f"🏆 RANKING – {okres.name}\n"
    for i, (user, score) in enumerate(rows, 1):
        result += f"\n{i}. <@{user}> — {score} pkt"
    if not rows:
        result += "\nBrak punktów."
    await interaction.response.send_message(result)

@bot.tree.command(
    name="cofnij",
    description="Cofnij swoje ostatnie zadanie"
)
@discord.app_commands.guild_only()
async def cofnij(interaction):
    row = db.execute(
        """SELECT id FROM points
        WHERE guild=? AND user=? AND day=?
        ORDER BY id DESC LIMIT 1""",
        (interaction.guild_id,
         interaction.user.id, today())
    ).fetchone()
    if row:
        db.execute(
            "DELETE FROM points WHERE id=?",
            (row[0],)
        )
        db.commit()
        await interaction.response.send_message(
            "↩️ Cofnięto ostatnie zadanie.",
            ephemeral=True
        )
    else:
        await interaction.response.send_message(
            "Nie masz dzisiaj żadnych zadań.",
            ephemeral=True
        )

@tasks.loop(seconds=30)
async def refresh():
    for guild, channel, message, day in db.execute(
        "SELECT * FROM boards"
    ).fetchall():
        try:
            ch = await bot.fetch_channel(channel)
            msg = await ch.fetch_message(message)
            await msg.edit(
                embed=board(guild),
                view=BoardView()
            )
            db.execute(
                "UPDATE boards SET day=? WHERE guild=?",
                (today(), guild)
            )
            db.commit()
        except discord.HTTPException as error:
            print(error)

@refresh.before_loop
async def before_refresh():
    await bot.wait_until_ready()

bot.run(TOKEN)
