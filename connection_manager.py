from fastapi import WebSocket, WebSocketDisconnect
from database import database
from typing import List, Dict

class ConnectionManager:
    def __init__(self):
        self.active_connections: List[WebSocket] = []
        self.chat_histories: Dict[int, List[str]] = {}

    async def connect(self, websocket: WebSocket, member_num: int, book_id: int):
        try:
            await websocket.accept()
            print(f"[WebSocket 연결] member_num: {member_num}, book_id: {book_id}")
            
            self.active_connections.append(websocket)
            chat_id = await self.get_or_create_chat_id(member_num, book_id)
            if chat_id not in self.chat_histories:
                query = "SELECT chat_content, sender_id FROM chating_content WHERE chat_id = :chat_id ORDER BY timestamp ASC"
                rows = await database.fetch_all(query, values={"chat_id": chat_id})
                self.chat_histories[chat_id] = [{"sender_id": row["sender_id"], "message": row["chat_content"]} for row in rows]
                # print(f"[기존 채팅 불러오기] chat_id: {chat_id}, history: {self.chat_histories[chat_id]}")

                for entry in self.chat_histories[chat_id]:
                    await websocket.send_json(entry)
        except WebSocketDisconnect:
            print(f"[WebSocket 연결 끊김] member_num: {member_num}, book_id: {book_id}")
            self.disconnect(websocket, chat_id)
        except Exception as e:
            print(f"[WebSocket 연결 오류] {e}")
            await websocket.close()  # 오류 발생 시 WebSocket을 닫기
        return chat_id

    async def load_chat_history(self, chat_id: int) -> List[dict]:
        query = "SELECT chat_content, sender_id FROM chating_content WHERE chat_id = :chat_id ORDER BY timestamp ASC"
        rows = await database.fetch_all(query, values={"chat_id": chat_id})
        return [{"sender_id": row["sender_id"], "message": row["chat_content"]} for row in rows]

    def disconnect(self, websocket: WebSocket, chat_id: int):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)
            print(f"[WebSocket 연결 해제] chat_id: {chat_id}")

    async def broadcast(self, websocket: WebSocket, message: dict):
        print(f"[메시지 브로드캐스트] message: {message}")
        try:
            await websocket.send_json(message)
        except WebSocketDisconnect:
            self.disconnect(websocket, 0)

    async def get_or_create_chat_id(self, member_num: int, book_id: int) -> int:
        if book_id == 0:
            return 0
        query = "SELECT chat_id FROM chatbot WHERE member_num = :member_num AND book_id = :book_id"
        result = await database.fetch_one(query, values={"member_num": member_num, "book_id": book_id})

        if result:
            return result["chat_id"]
        
        create_query = """
        INSERT INTO chatbot (book_id, member_num) 
        VALUES (:book_id, :member_num) 
        ON CONFLICT DO NOTHING 
        RETURNING chat_id
        """
        chat_id = await database.execute(create_query, values={"book_id": book_id, "member_num": member_num})

        if chat_id is None:
            result = await database.fetch_one(query, values={"member_num": member_num, "book_id": book_id})
            return result["chat_id"] if result else None
        
        return chat_id
