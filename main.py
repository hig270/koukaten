# main.py (Pylance完全静音版)
from __future__ import annotations

from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
import mysql.connector
import os, json, base64, asyncio
import numpy as np
from dotenv import load_dotenv
from datetime import datetime
from typing import Any, Optional, Dict, cast

load_dotenv()
app = FastAPI()

# ===== CORS =====
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ===== DB設定 =====
DB_CONFIG: Dict[str, Any] = {
    "host": os.getenv("DB_HOST"),
    "user": os.getenv("DB_USER"),
    "password": os.getenv("DB_PASSWORD"),
    "database": os.getenv("DB_NAME"),
}

MATCH_METRIC: str = (os.getenv("MATCH_METRIC") or "cosine").lower()
MATCH_THRESHOLD: float = float(os.getenv("MATCH_THRESHOLD") or 0.60)


def get_connection() -> Any:
    """mysql.connector.connect() は PooledMySQLConnection を返すため Any にする"""
    conn: Any = mysql.connector.connect(**DB_CONFIG)
    return conn


# ===== 類似度 =====
def cosine_sim(a: np.ndarray, b: np.ndarray) -> float:
    denom = float(np.linalg.norm(a) * np.linalg.norm(b))
    if denom == 0:
        return -1.0
    return float(np.dot(a, b) / denom)


def is_same_person(new_emb_list: list[float], stored_emb_list: list[float]) -> bool:
    a = np.array(new_emb_list, dtype=np.float32)
    b = np.array(stored_emb_list, dtype=np.float32)
    if a.shape != b.shape or a.size == 0:
        return False
    if MATCH_METRIC == "cosine":
        sim = cosine_sim(a, b)
        return sim >= MATCH_THRESHOLD
    dist = float(np.linalg.norm(a - b))
    return dist <= MATCH_THRESHOLD


def b64_to_bytes(s: Optional[str]) -> Optional[bytes]:
    if not s:
        return None
    try:
        return base64.b64decode(s, validate=True)
    except Exception:
        try:
            return base64.b64decode(s)
        except Exception:
            return None


# ===== SSE =====
subscribers: set[asyncio.Queue[Dict[str, Any]]] = set()


async def publish(event: Dict[str, Any]) -> None:
    dead: list[asyncio.Queue[Dict[str, Any]]] = []
    for q in list(subscribers):
        try:
            await q.put(event)
        except Exception:
            dead.append(q)
    for q in dead:
        subscribers.discard(q)


@app.get("/api/v1/stream/inside")
async def stream_inside():
    async def event_generator(q: asyncio.Queue[Dict[str, Any]]):
        try:
            await q.put({"type": "hello"})
            while True:
                msg = await q.get()
                yield f"data: {json.dumps(msg, ensure_ascii=False)}\n\n"
        except asyncio.CancelledError:
            pass

    q: asyncio.Queue[Dict[str, Any]] = asyncio.Queue()
    subscribers.add(q)
    return StreamingResponse(event_generator(q), media_type="text/event-stream")


# ===== メインAPI =====
@app.post("/api/v1/face-event")
async def receive_face_event(request: Request):
    data: Dict[str, Any] = await request.json()

    # --- 必須チェック ---
    idempotency_key = data.get("idempotencyKey")
    if not isinstance(idempotency_key, str):
        raise HTTPException(status_code=400, detail="idempotencyKey is required")

    emb_raw = data.get("embedding")
    if not isinstance(emb_raw, list) or len(emb_raw) == 0:
        raise HTTPException(status_code=400, detail="embedding list is required")

    new_emb: list[float] = [float(x) for x in emb_raw]

    face_score_raw = data.get("faceScore")
    face_score: float = (
        float(face_score_raw) if isinstance(face_score_raw, (int, float, str)) else 0.0
    )

    face_img_data: Optional[str] = None
    if isinstance(data.get("faceImage"), dict):
        face_img_data = cast(Dict[str, Any], data["faceImage"]).get("data")
    face_img_bin = b64_to_bytes(face_img_data)

    conn = get_connection()
    cur = conn.cursor(dictionary=True)

    try:
        # --- 冪等INSERT ---
        try:
            cur.execute(
                """
                INSERT INTO log (idempotencyKey, state, timestamp, raw_json)
                VALUES (%s, %s, %s, %s)
                """,
                (
                    idempotency_key,
                    "未判定",
                    datetime.now(),
                    json.dumps(data, ensure_ascii=False),
                ),
            )
            conn.commit()
        except mysql.connector.Error as e:
            if getattr(e, "errno", None) == 1062:
                cur.close()
                conn.close()
                return {"status": "duplicate", "message": "Already processed"}
            raise

        # --- 照合 ---
        cur.execute("SELECT * FROM members")
        members: list[Dict[str, Any]] = cast(list[Dict[str, Any]], cur.fetchall())

        matched_member: Optional[Dict[str, Any]] = None
        for m in members:
            emb_field = m.get("embedding")
            if not emb_field:
                continue

            emb_str: str
            if isinstance(emb_field, (bytes, bytearray)):
                emb_str = emb_field.decode("utf-8")
            elif isinstance(emb_field, (dict, list)):
                emb_str = json.dumps(emb_field)
            else:
                emb_str = str(emb_field)

            try:
                stored_emb: list[float] = json.loads(emb_str)
            except Exception:
                continue

            if is_same_person(new_emb, stored_emb):
                matched_member = m
                break

        # --- 未登録 ---
        if matched_member is None:
            cur.execute(
                """
                INSERT INTO members (name, studentNumber, inside, embedding, faceScore, faceImage)
                VALUES (%s, %s, %s, %s, %s, %s)
                """,
                ("", "", True, json.dumps(new_emb), face_score, face_img_bin),
            )
            conn.commit()
            last_id = cur.lastrowid
            user_id: int = int(last_id) if last_id is not None else 0
            state = "入室"

        # --- 既存 ---
        else:
            raw_user_id = matched_member.get("userId")
            user_id = int(raw_user_id) if raw_user_id is not None else 0
            inside_prev = bool(matched_member.get("inside") or False)
            inside_now = not inside_prev

            cur.execute(
                "UPDATE members SET inside = %s WHERE userId = %s",
                (inside_now, user_id),
            )
            conn.commit()

            state = "入室" if inside_now else "退室"

            # --- faceScoreが高ければ更新 ---
            old_score_val = matched_member.get("faceScore", 0.0)
            old_score = (
                float(old_score_val)
                if isinstance(old_score_val, (int, float, str))
                else 0.0
            )
            if face_score > old_score:
                cur.execute(
                    """
                    UPDATE members
                    SET embedding = %s, faceScore = %s, faceImage = %s
                    WHERE userId = %s
                    """,
                    (json.dumps(new_emb), face_score, face_img_bin, user_id),
                )
                conn.commit()

        # --- log更新 ---
        cur.execute(
            "SELECT name, studentNumber FROM members WHERE userId = %s", (user_id,)
        )
        result = cur.fetchone()
        r: Dict[str, Any] = cast(Dict[str, Any], result or {})
        name_val = r.get("name") if isinstance(r.get("name"), str) else ""
        sn_val = r.get("studentNumber") if isinstance(r.get("studentNumber"), str) else ""

        cur.execute(
            """
            UPDATE log
            SET userId = %s, name = %s, studentNumber = %s, state = %s
            WHERE idempotencyKey = %s
            """,
            (user_id, name_val, sn_val, state, idempotency_key),
        )
        conn.commit()

        # --- SSE通知 ---
        await publish({"type": "inside_changed", "userId": user_id, "state": state})

        return {"status": "success", "state": state, "userId": user_id}

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        try:
            cur.close()
            conn.close()
        except Exception:
            pass


@app.get("/api/v1/inside")
def list_inside():
    conn = get_connection()
    cur = conn.cursor(dictionary=True)
    cur.execute("SELECT userId, name, studentNumber FROM inside_persons")
    rows: list[Dict[str, Any]] = cast(list[Dict[str, Any]], cur.fetchall())
    cur.close()
    conn.close()
    return {"items": rows}


@app.patch("/api/v1/members/{userId}")
async def update_member(userId: int, request: Request):
    body: Dict[str, Any] = await request.json()
    name: str = str(body.get("name") or "")
    studentNumber: str = str(body.get("studentNumber") or "")

    import re
    if studentNumber and not re.fullmatch(r"[a-z]\d{5}", studentNumber):
        raise HTTPException(status_code=400, detail="studentNumber must match [a-z][0-9]{5}")

    conn = get_connection()
    cur = conn.cursor()
    try:
        cur.execute(
            "UPDATE members SET name = %s, studentNumber = %s WHERE userId = %s",
            (name, studentNumber, userId),
        )
        conn.commit()
        await publish({"type": "inside_changed", "userId": userId, "state": "updated"})
        return {"status": "ok"}
    finally:
        cur.close()
        conn.close()

@app.get("/api/v1/members/unregistered")
def list_unregistered_members():
    conn = get_connection()
    cur = conn.cursor(dictionary=True)
    cur.execute("""
        SELECT
            userId,
            name,
            studentNumber,
            TO_BASE64(faceImage) AS faceImage
        FROM members
        WHERE name = '' OR name IS NULL
        ORDER BY userId ASC
    """)
    rows = cur.fetchall()
    cur.close()
    conn.close()
    return {"items": rows}

@app.get("/api/v1/members/registered")
def list_registered_members():
    conn = get_connection()
    cur = conn.cursor(dictionary=True)
    cur.execute("""
        SELECT
            userId,
            name,
            studentNumber,
            TO_BASE64(faceImage) AS faceImage
        FROM members
        WHERE name IS NOT NULL AND name <> ''
        ORDER BY studentNumber ASC
    """)
    rows = cur.fetchall()
    cur.close()
    conn.close()
    return {"items": rows}


@app.get("/")
def root():
    return {"message": "FastAPI (no warnings) is running!"}
