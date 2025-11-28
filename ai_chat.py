import logging
import re
import random
from groq import Groq
from telegram import Update
from telegram.ext import ContextTypes
from collections import defaultdict

# ==========================================
# ⚙️ CONFIGURATION
# ==========================================
GROQ_API_KEY = "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"

try:
    client = Groq(api_key=GROQ_API_KEY)
except Exception as e:
    logging.error(f"Failed to connect to Groq: {e}")

# 🎭 STICKERS (Keep these, they are fine for replies)
NARUTO_STICKERS = [
    "CAACAgIAAyEFAAS4-2ltAAIN4mkiiI2paXLgv-hx5FMXEcr_6wKBAAJYHgACI_UgSOHPL9CJ-P-pHgQ",
    "CAACAgUAAyEFAAS4-2ltAAIN2mkih_VB8Pp10HgcWuuDEwhN660gAALPCQACSwyhVZFJXBGBB10AAR4E",
    "CAACAgUAAyEFAAS4-2ltAAIN22kiiAUKJpTFeWmmMqsBeMKFZd2HAAJSCAACmszQVAnAFXlBAjNSHgQ"
]

# 🧠 MEMORY
CHAT_HISTORY = defaultdict(list) 

# 🔥 SMART SYSTEM PROMPT (Like ChatGPT)
SYSTEM_PROMPT = """
You are **Naruto Uzumaki**, the Seventh Hokage. 
However, you act as a **Smart AI Assistant** (similar to ChatGPT).

**YOUR RULES:**
1. **Be Intelligent:** Answer questions properly (Coding, Math, Life, General Knowledge).
2. **Be Mature:** Do NOT act childish. No forced catchphrases (like Dattebayo) unless it fits perfectly.
3. **Be Helpful:** Your goal is to help the user, not to be a "character".
4. **Language:** - User English -> You English.
   - User Hindi -> You Hindi.
   - Keep answers clear and concise.

**RESTRICTIONS:**
- **NO CRINGE:** No Shayari, no bad jokes, no random emojis unless necessary.
- **NO EXTRA TALK:** Get straight to the point.
"""

async def naruto_chat_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message:
        return
    
    chat_id = update.effective_chat.id
    
    # 1. CHECK IF REPLIED TO BOT
    is_reply_to_bot = False
    if update.message.reply_to_message:
        if update.message.reply_to_message.from_user.id == context.bot.id:
            is_reply_to_bot = True

    # ==========================================
    # 🎭 PART 1: STICKER HANDLING
    # ==========================================
    if update.message.sticker and is_reply_to_bot:
        if NARUTO_STICKERS:
            try:
                random_sticker = random.choice(NARUTO_STICKERS)
                await update.message.reply_sticker(random_sticker)
            except Exception as e:
                logging.error(f"Sticker Error: {e}")
        return 

    # ==========================================
    # 📝 PART 2: TEXT HANDLING
    # ==========================================
    if not update.message.text:
        return

    user_text = update.message.text
    text_lower = user_text.lower()

    # 🔥 ONLY ONE TRIGGER: "NARUTO"
    # It will ONLY reply if someone types "naruto" (whole word) OR replies to the bot.
    triggers = ["naruto"]
    
    pattern = r"\b(?:" + "|".join(map(re.escape, triggers)) + r")\b"
    found_trigger = re.search(pattern, text_lower)
    
    should_reply = found_trigger or is_reply_to_bot

    if should_reply:
        await context.bot.send_chat_action(chat_id=chat_id, action="typing")

        try:
            history = CHAT_HISTORY[chat_id]
            messages_payload = [{"role": "system", "content": SYSTEM_PROMPT}]
            messages_payload.extend(history)
            messages_payload.append({"role": "user", "content": user_text})

            chat_completion = client.chat.completions.create(
                messages=messages_payload,
                model="llama-3.1-8b-instant", 
                temperature=0.6,   # 🔥 Lower temp = More logical/smart, less random
                max_tokens=300,    # 🔥 Increased limit so it can give detailed answers
            )

            ai_reply = chat_completion.choices[0].message.content

            # Memory
            CHAT_HISTORY[chat_id].append({"role": "user", "content": user_text})
            CHAT_HISTORY[chat_id].append({"role": "assistant", "content": ai_reply})
            if len(CHAT_HISTORY[chat_id]) > 6:
                CHAT_HISTORY[chat_id] = CHAT_HISTORY[chat_id][-6:]

            await update.message.reply_text(ai_reply)

        except Exception as e:
            logging.error(f"Error in AI Chat: {e}")
