import asyncio, time, logging
from .ai import ai_service
from .database import pool

async def run_worker():
    MAX_RETRIES = 3
    BACKOFF = [5, 15, 45]

    while True:
        async with pool.acquire() as conn:
            # CRASH RECOVERY: ၂ မိနစ်ကျော်Processing ဖြစ်နေတာတွေကို Pending ပြန်လုပ်မယ်
            await conn.execute("UPDATE task_queue SET status='pending' WHERE status='processing' AND updated_at < NOW() - INTERVAL '2 minutes'")

            # GET TASK: Atomic Lock သုံးပြီး ယူမယ်
            task = await conn.fetchrow("""
                UPDATE task_queue SET status='processing', updated_at=NOW()
                WHERE id = (SELECT id FROM task_queue WHERE status='pending' ORDER BY id ASC LIMIT 1 FOR UPDATE SKIP LOCKED)
                RETURNING *
            """)

            if not task:
                await asyncio.sleep(2); continue

            start_time = time.time()
            try:
                # AI Processing
                res_json, model = await ai_service.get_order_json(task['user_text'])
                
                # Logic to Send Telegram Message Here
                # await send_tg(task['chat_id'], f"အော်ဒါလက်ခံရရှိပါပြီ: {res_json}")

                # Success
                await conn.execute("UPDATE task_queue SET status='completed' WHERE id=$1", task['id'])
                
                # Log for observability
                duration = int((time.time() - start_time) * 1000)
                await conn.execute("INSERT INTO ai_logs (shop_id, model_used, status, response_time_ms) VALUES ($1,$2,$3,$4)", 
                                   task['shop_id'], model, 'SUCCESS', duration)

            except Exception as e:
                attempts = task['attempts'] + 1
                if attempts >= MAX_RETRIES:
                    # Move to Dead Letter Queue
                    await conn.execute("INSERT INTO dead_letter_tasks (shop_id, user_text, last_error) VALUES ($1,$2,$3)",
                                       task['shop_id'], task['user_text'], str(e))
                    await conn.execute("DELETE FROM task_queue WHERE id=$1", task['id'])
                else:
                    # Retry with Backoff
                    await asyncio.sleep(BACKOFF[attempts-1])
                    await conn.execute("UPDATE task_queue SET status='pending', attempts=$2, last_error=$3 WHERE id=$1",
                                       task['id'], attempts, str(e))

if __name__ == "__main__":
    asyncio.run(run_worker())
