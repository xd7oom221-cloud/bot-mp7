import discord
from discord.ext import commands
from discord import app_commands
import datetime
import re

intents = discord.Intents.default()
intents.members = True
intents.message_content = True

bot = commands.Bot(command_prefix="!", intents=intents)

# ------------------- الإعدادات المتغيرة -------------------
PAIRS = {
    1554489401445187737: 1554489401479012414,  # SPECIAL CAR -> سحب SPECIAL CAR
    1554924853117718548: 1554927314549342249,  # GOLD -> سحب GOLD
    1555846078736367646: 1554927357352214718,  # حزمة المواطنين vip -> سحب vip
    1554925119535579216: 1554927440902627419,  # حزمة التهريب -> سحب حزمة التهريب
    1555423192255045713: 1554927515544584213,  # حزمة المرهمات -> سحب حزمة المرهمات
}

LOG_CHANNEL_ID = 1558423955298328679          # روم سجلات السحب (Log)
STRIP_CHANNEL_ID = 1554489405861789729        # روم إنذارات الحزم (المخصص لاستخدام أمر السحب)
PACKAGES_ADMIN_ROLE_ID = 1555405306777829398     # رول مسؤول الحزم
HIGHER_ADMIN_ROLE_ID = 1554489401940246529       # رول مسؤول الإدارة العليا (لفك الحزم)
# -----------------------------------------------------------

def parse_duration_to_minutes(duration_str: str) -> int:
    """تحويل صيغ الوقت المختلفة إلى دقائق"""
    duration_str = duration_str.lower().strip()
    match = re.search(r'(\d+)\s*([dhmأياساعةدقيقة]?)', duration_str)
    if not match:
        return 0
    
    num = int(match.group(1))
    unit = match.group(2)

    if unit in ['d', 'ي', 'أ']:
        return num * 24 * 60
    elif unit in ['h', 'س']:
        return num * 60
    elif unit in ['m', 'د']:
        return num
    else:
        return num * 24 * 60

def format_minutes_to_text(total_minutes: int) -> str:
    """تحويل الدقائق الإجمالية إلى نص عربي واضح"""
    days = total_minutes // (24 * 60)
    remaining_minutes = total_minutes % (24 * 60)
    hours = remaining_minutes // 60
    minutes = remaining_minutes % 60

    parts = []
    if days > 0:
        parts.append(f"{days} يوم")
    if hours > 0:
        parts.append(f"{hours} ساعة")
    if minutes > 0:
        parts.append(f"{minutes} دقيقة")
    
    return " و ".join(parts) if parts else "غير محدد"

@bot.event
async def on_ready():
    print(f'تم تسجيل الدخول بنجاح بواسطة {bot.user}')
    try:
        synced = await bot.tree.sync()
        print(f"تم مزامنة {len(synced)} أمر بنجاح.")
    except Exception as e:
        print(f"خطأ في المزامنة: {e}")

# ==================== 1. أمر سحب الحزم (لمسؤول الحزم وفي روم الإنذارات فقط) ====================
@bot.tree.command(name="سحب_كل_الحزم", description="سحب حزم العضو وتدبيل المدة وإعطائه رولات السحب")
@app_commands.describe(
    member="العضو المراد سحب حزمه",
    duration="مدة السحب (مثال: 2d أو 5d أو 3h)",
    reason="سبب سحب الحزم"
)
async def strip_packages(interaction: discord.Interaction, member: discord.Member, duration: str, reason: str):
    # 1. التحقق من القناة (يجب أن يكون في روم إنذارات الحزم فقط)
    if interaction.channel_id != STRIP_CHANNEL_ID:
        strip_channel = interaction.guild.get_channel(STRIP_CHANNEL_ID)
        channel_mention = strip_channel.mention if strip_channel else "روم إنذارات الحزم"
        await interaction.response.send_message(f"❌ هذا الأمر مخصص للاستخدام داخل {channel_mention} فقط!", ephemeral=True)
        return

    # 2. التحقق من الصلاحيات (مسؤول الحزم أو الإدارة العليا أو الأدمن)
    p_admin = interaction.guild.get_role(PACKAGES_ADMIN_ROLE_ID)
    h_admin = interaction.guild.get_role(HIGHER_ADMIN_ROLE_ID)
    
    if (p_admin not in interaction.user.roles and h_admin not in interaction.user.roles and not interaction.user.guild_permissions.administrator):
        await interaction.response.send_message("❌ عفواً، هذا الأمر مخصص لـ **مسؤول الحزم** فقط!", ephemeral=True)
        return

    await interaction.response.defer(ephemeral=True)

    roles_to_remove = []
    roles_to_add = []
    removed_names = []
    added_names = []

    for main_role_id, stripped_role_id in PAIRS.items():
        main_role = interaction.guild.get_role(main_role_id)
        if main_role and main_role in member.roles:
            roles_to_remove.append(main_role)
            removed_names.append(main_role.mention)
            
            stripped_role = interaction.guild.get_role(stripped_role_id)
            if stripped_role:
                roles_to_add.append(stripped_role)
                added_names.append(stripped_role.mention)

    has_existing_strip = any(
        interaction.guild.get_role(s_id) in member.roles 
        for s_id in PAIRS.values() if interaction.guild.get_role(s_id)
    )

    if not roles_to_remove and not has_existing_strip:
        await interaction.followup.send(f"⚠️ العضو {member.mention} لا يمتلك أي حزم أساسية ولا يوجد لديه سحب نشط.", ephemeral=True)
        return

    new_minutes = parse_duration_to_minutes(duration)
    total_minutes = new_minutes

    log_channel = interaction.guild.get_channel(LOG_CHANNEL_ID)
    
    # البحث في السجل عن مدة سابقة لتراكم الأيام
    if has_existing_strip and log_channel:
        async for message in log_channel.history(limit=50):
            if message.embeds:
                embed = message.embeds[0]
                if embed.fields and any(f"({member.id})" in f.value for f in embed.fields if "العضو" in f.name):
                    for field in embed.fields:
                        if "المدة الإجمالية" in field.name or "مدة" in field.name:
                            old_minutes = parse_duration_to_minutes(field.value)
                            total_minutes += old_minutes
                            break
                    break

    final_duration_text = format_minutes_to_text(total_minutes)
    new_duration_text = format_minutes_to_text(new_minutes)

    if roles_to_remove:
        await member.remove_roles(*roles_to_remove, reason=f"سحب حزم بواسطة {interaction.user.name}")
    if roles_to_add:
        await member.add_roles(*roles_to_add, reason=f"إعطاء رولات سحب الحزم بواسطة {interaction.user.name}")

    removed_str = "\n• " + "\n• ".join(removed_names) if removed_names else "العضو مسحوب مسبقاً"
    added_str = "\n• " + "\n• ".join(added_names) if added_names else "رولات السحب مطبقة بالفعل"

    # إرسال إشعار الخاص
    dm_embed = discord.Embed(
        title="⚠️ تنبيه: تم (سحب/تعديل) حزمك العسكرية",
        color=discord.Color.red(),
        timestamp=datetime.datetime.now()
    )
    dm_embed.add_field(name="السبب", value=reason, inline=False)
    dm_embed.add_field(name="المدة المضافة", value=new_duration_text, inline=True)
    dm_embed.add_field(name="المدة الإجمالية للطلب/السحب", value=final_duration_text, inline=True)
    dm_embed.add_field(name="الحزم المسحوبة", value=removed_str, inline=False)
    dm_embed.set_footer(text=f"السيرفر: {interaction.guild.name}")

    try:
        await member.send(embed=dm_embed)
        dm_status = "✅ تم إرسال إشعار الخاص للعضو."
    except discord.Forbidden:
        dm_status = "⚠️ الخاص مغلق لدى العضو."

    # إرسال السجل الموثق في روم LOG
    if log_channel:
        log_embed = discord.Embed(
            title="📋 سجل سحب وتدبيل الحزم (LOG)",
            color=discord.Color.dark_red(),
            timestamp=datetime.datetime.now()
        )
        log_embed.add_field(name="العضو المستهدف", value=f"{member.mention} (`{member.id}`)", inline=False)
        log_embed.add_field(name="مسؤول الحزم المنفذ للأمر", value=f"{interaction.user.mention} (`{interaction.user.id}`)", inline=False)
        log_embed.add_field(name="المدة المضافة الجديدة", value=new_duration_text, inline=True)
        log_embed.add_field(name="المدة الإجمالية (بعد التدبيل)", value=final_duration_text, inline=True)
        log_embed.add_field(name="السبب", value=reason, inline=False)
        log_embed.add_field(name="الحزم المسحوبة", value=removed_str, inline=False)
        log_embed.set_thumbnail(url=member.display_avatar.url)
        await log_channel.send(embed=log_embed)

    await interaction.followup.send(f"✅ تم سحب/تدبيل حزم {member.mention} بنجاح.\n⏱️ المدة الإجمالية الجديدة: **{final_duration_text}**.\n{dm_status}", ephemeral=True)


# ==================== 2. أمر فك الحزم (الإدارة العليا) ====================
@bot.tree.command(name="فك_الحزم", description="فك الحزم عن العضو وإرجاع رولاته الأساسية (خاص بالإدارة العليا)")
@app_commands.describe(
    member="العضو المراد فك الحزم عنه",
    reason="سبب فك الحزم"
)
async def unstrip_packages(interaction: discord.Interaction, member: discord.Member, reason: str):
    higher_admin_role = interaction.guild.get_role(HIGHER_ADMIN_ROLE_ID)
    if higher_admin_role not in interaction.user.roles and not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("❌ عفواً، أمر **فك الحزم** مخصص لـ **مسؤول الإدارة العليا** فقط!", ephemeral=True)
        return

    await interaction.response.defer(ephemeral=True)

    stripped_to_remove = []
    main_to_add = []
    restored_names = []

    for main_role_id, stripped_role_id in PAIRS.items():
        stripped_role = interaction.guild.get_role(stripped_role_id)
        if stripped_role and stripped_role in member.roles:
            stripped_to_remove.append(stripped_role)
            
            main_role = interaction.guild.get_role(main_role_id)
            if main_role:
                main_to_add.append(main_role)
                restored_names.append(main_role.mention)

    if not stripped_to_remove:
        await interaction.followup.send(f"⚠️ العضو {member.mention} لا يمتلك أي رولات سحب نشطة.", ephemeral=True)
        return

    await member.remove_roles(*stripped_to_remove, reason=f"فك الحزم بواسطة الإدارة العليا: {interaction.user.name}")
    if main_to_add:
        await member.add_roles(*main_to_add, reason=f"إرجاع الحزم بواسطة الإدارة العليا: {interaction.user.name}")

    restored_str = "\n• " + "\n• ".join(restored_names)

    # الخاص
    try:
        dm_embed = discord.Embed(
            title="✨ تم فك الحزم عنك وإرجاعها",
            color=discord.Color.green(),
            timestamp=datetime.datetime.now()
        )
        dm_embed.add_field(name="السبب", value=reason, inline=False)
        dm_embed.add_field(name="الحزم المستعادة", value=restored_str, inline=False)
        await member.send(embed=dm_embed)
    except discord.Forbidden:
        pass

    # Log
    log_channel = interaction.guild.get_channel(LOG_CHANNEL_ID)
    if log_channel:
        log_embed = discord.Embed(
            title="🔓 سجل فك الحزم (LOG)",
            color=discord.Color.green(),
            timestamp=datetime.datetime.now()
        )
        log_embed.add_field(name="العضو المستهدف", value=f"{member.mention} (`{member.id}`)", inline=False)
        log_embed.add_field(name="مسؤول الإدارة العليا المنفذ", value=f"{interaction.user.mention} (`{interaction.user.id}`)", inline=False)
        log_embed.add_field(name="السبب", value=reason, inline=False)
        log_embed.add_field(name="الحزم التي تم إرجاعها", value=restored_str, inline=False)
        log_embed.set_thumbnail(url=member.display_avatar.url)
        await log_channel.send(embed=log_embed)

    await interaction.followup.send(f"✅ تم فك الحزم عن {member.mention} وإرجاع رولاته بنجاح.", ephemeral=True)

# ضع توكن البوت الخاص بك هنا
bot.run("YOUR_BOT_TOKEN_HERE")