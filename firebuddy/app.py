import asyncio
import contextlib
from contextlib import asynccontextmanager

from fastapi import FastAPI, Form, HTTPException, Request
from fastapi.responses import Response

from firebuddy import agent, config, db, monitor, router, sms


async def _monitor_loop() -> None:
    while True:
        try:
            with db.session() as conn:
                monitor.run_once(conn, sms.send)
        except Exception as exc:  # keep the loop alive across transient failures
            print(f"[MONITOR ERROR] {exc}")
        await asyncio.sleep(config.MONITOR_INTERVAL_SEC)


@asynccontextmanager
async def _lifespan(app: FastAPI):
    with db.session() as conn:
        db.init_db(conn)
    task = asyncio.create_task(_monitor_loop())
    try:
        yield
    finally:
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task


app = FastAPI(title="FireBuddy", lifespan=_lifespan)


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.post("/sms")
async def sms_webhook(request: Request, From: str = Form(...), Body: str = Form(...)):
    if not config.DRY_RUN:
        signature = request.headers.get("X-Twilio-Signature", "")
        form = await request.form()
        url = config.PUBLIC_BASE_URL.rstrip("/") + "/sms"
        if not sms.verify_twilio_signature(url, dict(form), signature):
            raise HTTPException(status_code=403, detail="Invalid Twilio signature")

    with db.session() as conn:
        llm_client = agent.AnthropicLLMClient() if config.ANTHROPIC_API_KEY else None
        reply = router.route_message(conn, From, Body, llm_client)

    if reply:
        sms.send(From, reply)

    return Response(content="<Response></Response>", media_type="text/xml")
