from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from connection_manager import ConnectionManager
from chat_model import create_prompt, chat_model
from database import database
import re

router = APIRouter()
manager = ConnectionManager()

@router.get("/chat-list/{member_num}")
async def get_chat_rooms(member_num: int):
    query = """
    SELECT cb.book_id, b.book_title
    FROM chatbot cb
    JOIN book b ON cb.book_id = b.book_id
    WHERE cb.member_num = :member_num
    """
    rows = await database.fetch_all(query, values={"member_num": member_num})
    return [{"book_id": row["book_id"], "book_title": row["book_title"]} for row in rows]

@router.websocket("/ws/chat")
async def websocket_endpoint(websocket: WebSocket, member_num: int, book_id: int = 0):
    print(f"[WebSocket 요청 수신] member_num: {member_num}, book_id: {book_id}")
    
    if book_id == 0:
        await websocket.accept()
        chat_id = 0
        print(f"[일회성 채팅] member_num: {member_num}, book_id: {book_id}, chat_id: {chat_id}")
    else:
        chat_id = await manager.connect(websocket, member_num, book_id)
        print(f"[지속적 채팅] member_num: {member_num}, book_id: {book_id}, chat_id: {chat_id}")

    try:
        while True:
            data = await websocket.receive_json()
            print(f"[메시지 수신] data: {data}")
            if not data.get("message", "").strip():
                continue

            user_message = data["message"]

            # 다양한 요청 감지 (정규 표현식 사용)
            if re.search(r"(이\s*책\s*설명해줘|책\s*(에\s*(대해|관해|관한)?\s*)?(내용|설명|소개|이야기|알려줘|알려\s*줄래|어떤\s*(책|내용)|무엇|뭐야|해줘|얘기해줘|알고\s*싶어|얘기해볼까|뭘까|설명해줘|얘기할\s*수\s*있어|알려줄래|얘기해\s*줄\s*수\s*있어|어떤\s*내용이야|어떤\s*내용|어떤\s*내용인지|어떤\s*내용일까|내용을\s*알려줘|설명을\s*알려줘))", user_message, re.IGNORECASE):
                if book_id != 0:
                    book_title_query = "SELECT book_title FROM book WHERE book_id = :book_id"
                    book_title = await database.fetch_one(book_title_query, values={"book_id": book_id})

                    if book_title:
                        title_text = book_title['book_title']
                        prompt_message = f"{title_text}라는 책에 대해 설명해줘."
                        response = await chat_model.agenerate([prompt_message])
                        bot_message_content = response.generations[0][0].text.strip()
                    else:
                        bot_message_content = "죄송합니다, 해당 책에 대한 정보를 찾을 수 없습니다."
                else:
                    response = await chat_model.agenerate([user_message])
                    bot_message_content = response.generations[0][0].text.strip()

                stella_message = {"sender_id": "stella", "message": bot_message_content}
                
                if chat_id != 0:
                    manager.chat_histories[chat_id].append(data)
                    manager.chat_histories[chat_id].append(stella_message)

                    save_query = "INSERT INTO chating_content (chat_id, chat_content, sender_id) VALUES (:chat_id, :chat_content, :sender_id)"
                    await database.execute(save_query, values={"chat_id": chat_id, "chat_content": user_message, "sender_id": "user"})
                    await database.execute(save_query, values={"chat_id": chat_id, "chat_content": bot_message_content, "sender_id": "stella"})
                
                await websocket.send_json(stella_message)
            else:
                chat_history = "\n".join([entry["message"] for entry in manager.chat_histories.get(chat_id, [])])
                formatted_prompt = create_prompt(chat_history, user_message)
                
                response = await chat_model.agenerate([formatted_prompt])
                bot_message_content = response.generations[0][0].text.strip()

                user_message = {"sender_id": "user", "message": user_message}
                stella_message = {"sender_id": "stella", "message": bot_message_content}
                
                if chat_id != 0:
                    manager.chat_histories[chat_id].append(user_message)
                    manager.chat_histories[chat_id].append(stella_message)
                    
                    save_query = "INSERT INTO chating_content (chat_id, chat_content, sender_id) VALUES (:chat_id, :chat_content, :sender_id)"
                    await database.execute(save_query, values={"chat_id": chat_id, "chat_content": user_message["message"], "sender_id": "user"})
                    await database.execute(save_query, values={"chat_id": chat_id, "chat_content": bot_message_content, "sender_id": "stella"})

                await manager.broadcast(websocket, stella_message)
    except WebSocketDisconnect:
        print(f"[WebSocket 연결 끊김] chat_id: {chat_id}, member_num: {member_num}, book_id: {book_id}")
        if book_id != 0:
            manager.disconnect(websocket, chat_id)

# HTTP 엔드포인트 - 채팅 내역 가져오기
@router.get("/chat/{book_id}/{member_num}")
async def get_chat_history(book_id: int, member_num: int):
    query = """
    SELECT cc.chat_content, cc.sender_id
    FROM chating_content cc
    JOIN chatbot cb ON cb.chat_id = cc.chat_id
    WHERE cb.book_id = :book_id AND cb.member_num = :member_num
    ORDER BY cc.timestamp ASC
    """
    rows = await database.fetch_all(query, values={"book_id": book_id, "member_num": member_num})
    chat_history = [{"sender_id": row["sender_id"], "message": row["chat_content"]} for row in rows]
    return chat_history

# 루트 엔드포인트
@router.get("/")
async def root():
    return {"message": "Chatbot server is running"}
