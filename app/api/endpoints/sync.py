import time
import logging
from fastapi import APIRouter, Depends, HTTPException
from app.models import schemas
from app.core import security
from app.db import connection

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/sync", tags=["sync"])

@router.post("")
async def sync(
    req: schemas.SyncRequest,
    user_id: str = Depends(security.get_current_user_id),
    conn=Depends(connection.get_db_connection)
):
    server_timestamp = int(time.time() * 1000)
    try:
        with conn.cursor() as cur:
            # 1. Processar Favoritos do Cliente
            client_fav_ids = set()
            for fav in req.favorites:
                client_fav_ids.add(fav.id)
                # Verificar se já existe no banco remoto
                cur.execute(
                    "SELECT updated_at, is_deleted FROM favorites WHERE id = %s AND user_id = %s",
                    (fav.id, user_id)
                )
                row = cur.fetchone()
                if not row:
                    # Inserir novo
                    cur.execute(
                        """INSERT INTO favorites (id, user_id, type, book_slug, book_title, chapter_id, chapter_name, 
                                                 paragraph_number, paragraph_text, timestamp, group_id, group_range, 
                                                 updated_at, is_deleted)
                           VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
                        (fav.id, user_id, fav.type, fav.book_slug, fav.book_title, fav.chapter_id, fav.chapter_name,
                         fav.paragraph_number, fav.paragraph_text, fav.timestamp, fav.group_id, fav.group_range,
                         fav.updated_at, fav.is_deleted)
                    )
                else:
                    db_updated_at, db_is_deleted = row[0], row[1]
                    # Se o do cliente for mais recente, atualiza o banco
                    if fav.updated_at > db_updated_at:
                        cur.execute(
                            """UPDATE favorites SET type=%s, book_slug=%s, book_title=%s, chapter_id=%s, chapter_name=%s, 
                                                   paragraph_number=%s, paragraph_text=%s, timestamp=%s, group_id=%s, 
                                                   group_range=%s, updated_at=%s, is_deleted=%s 
                               WHERE id=%s AND user_id=%s""",
                            (fav.type, fav.book_slug, fav.book_title, fav.chapter_id, fav.chapter_name,
                             fav.paragraph_number, fav.paragraph_text, fav.timestamp, fav.group_id, fav.group_range,
                             fav.updated_at, fav.is_deleted, fav.id, user_id)
                        )

            # 2. Processar Grifos (Highlights) do Cliente
            client_hl_ids = set()
            for hl in req.highlights:
                client_hl_ids.add(hl.id)
                cur.execute(
                    "SELECT updated_at, is_deleted FROM highlights WHERE id = %s AND user_id = %s",
                    (hl.id, user_id)
                )
                row = cur.fetchone()
                if not row:
                    # Inserir novo
                    cur.execute(
                        """INSERT INTO highlights (id, user_id, type, book_slug, chapter_id, paragraph_number, 
                                                  start_word_index, end_word_index, highlighted_text, color, 
                                                  timestamp, end_paragraph_number, end_word_index_end, updated_at, is_deleted)
                           VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
                        (hl.id, user_id, hl.type, hl.book_slug, hl.chapter_id, hl.paragraph_number,
                         hl.start_word_index, hl.end_word_index, hl.highlighted_text, hl.color,
                         hl.timestamp, hl.end_paragraph_number, hl.end_word_index_end, hl.updated_at, hl.is_deleted)
                    )
                else:
                    db_updated_at, db_is_deleted = row[0], row[1]
                    if hl.updated_at > db_updated_at:
                        cur.execute(
                            """UPDATE highlights SET type=%s, book_slug=%s, chapter_id=%s, paragraph_number=%s, 
                                                     start_word_index=%s, end_word_index=%s, highlighted_text=%s, color=%s, 
                                                     timestamp=%s, end_paragraph_number=%s, end_word_index_end=%s, 
                                                     updated_at=%s, is_deleted=%s 
                               WHERE id=%s AND user_id=%s""",
                            (hl.type, hl.book_slug, hl.chapter_id, hl.paragraph_number,
                             hl.start_word_index, hl.end_word_index, hl.highlighted_text, hl.color,
                             hl.timestamp, hl.end_paragraph_number, hl.end_word_index_end, hl.updated_at, hl.is_deleted,
                             hl.id, user_id)
                        )

            # 3. Processar Chats do Cliente
            client_chat_ids = set()
            chats_payload = req.chats or []
            for chat in chats_payload:
                client_chat_ids.add(chat.id)
                cur.execute(
                    "SELECT updated_at, is_deleted FROM chats WHERE id = %s AND user_id = %s",
                    (chat.id, user_id)
                )
                row = cur.fetchone()
                if not row:
                    cur.execute(
                        """INSERT INTO chats (id, user_id, title, created_at, updated_at, messages_json, is_deleted)
                           VALUES (%s, %s, %s, %s, %s, %s, %s)""",
                        (chat.id, user_id, chat.title, chat.created_at, chat.updated_at, chat.messages_json, chat.is_deleted)
                    )
                else:
                    db_updated_at, db_is_deleted = row[0], row[1]
                    if chat.updated_at > db_updated_at:
                        cur.execute(
                            """UPDATE chats SET title=%s, created_at=%s, updated_at=%s, messages_json=%s, is_deleted=%s
                               WHERE id=%s AND user_id=%s""",
                            (chat.title, chat.created_at, chat.updated_at, chat.messages_json, chat.is_deleted, chat.id, user_id)
                        )

            # 3.5. Processar Atividades do Cliente
            client_activity_ids = set()
            activities_payload = req.activities or []
            for act in activities_payload:
                client_activity_ids.add(act.id)
                cur.execute(
                    "SELECT updated_at, is_deleted FROM activities WHERE id = %s AND user_id = %s",
                    (act.id, user_id)
                )
                row = cur.fetchone()
                if not row:
                    cur.execute(
                        """INSERT INTO activities (id, user_id, titulo, dia, horario, lembrete_ativo, 
                                                   lembrete_minutos_antes, repetir, frequencia, dias_semana, cor, 
                                                   mensagem_lembrete, terminar_tipo, terminar_vezes, terminar_data, 
                                                   icone, updated_at, is_deleted)
                           VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
                        (act.id, user_id, act.titulo, act.dia, act.horario, act.lembrete_ativo,
                         act.lembrete_minutos_antes, act.repetir, act.frequencia, act.dias_semana, act.cor,
                         act.mensagem_lembrete, act.terminar_tipo, act.terminar_vezes, act.terminar_data,
                         act.icone, act.updated_at, act.is_deleted)
                    )
                else:
                    db_updated_at, db_is_deleted = row[0], row[1]
                    if act.updated_at > db_updated_at:
                        cur.execute(
                            """UPDATE activities SET titulo=%s, dia=%s, horario=%s, lembrete_ativo=%s, 
                                                     lembrete_minutos_antes=%s, repetir=%s, frequencia=%s, dias_semana=%s, 
                                                     cor=%s, mensagem_lembrete=%s, terminar_tipo=%s, terminar_vezes=%s, 
                                                     terminar_data=%s, icone=%s, updated_at=%s, is_deleted=%s
                               WHERE id=%s AND user_id=%s""",
                            (act.titulo, act.dia, act.horario, act.lembrete_ativo,
                             act.lembrete_minutos_antes, act.repetir, act.frequencia, act.dias_semana, act.cor,
                             act.mensagem_lembrete, act.terminar_tipo, act.terminar_vezes, act.terminar_data,
                             act.icone, act.updated_at, act.is_deleted, act.id, user_id)
                        )

            # 3.6. Processar Conclusões de Atividades do Cliente
            client_completion_ids = set()
            completions_payload = req.completions or []
            for comp in completions_payload:
                client_completion_ids.add(comp.id)
                cur.execute(
                    "SELECT updated_at, is_deleted FROM activity_completions WHERE id = %s AND user_id = %s",
                    (comp.id, user_id)
                )
                row = cur.fetchone()
                if not row:
                    cur.execute(
                        """INSERT INTO activity_completions (id, user_id, activity_id, data, updated_at, is_deleted)
                           VALUES (%s, %s, %s, %s, %s, %s)""",
                        (comp.id, user_id, comp.activity_id, comp.data, comp.updated_at, comp.is_deleted)
                    )
                else:
                    db_updated_at, db_is_deleted = row[0], row[1]
                    if comp.updated_at > db_updated_at:
                        cur.execute(
                            """UPDATE activity_completions SET activity_id=%s, data=%s, updated_at=%s, is_deleted=%s
                               WHERE id=%s AND user_id=%s""",
                            (comp.activity_id, comp.data, comp.updated_at, comp.is_deleted, comp.id, user_id)
                        )

            # 3.7. Processar Exclusões de Atividades do Cliente
            client_exclusion_ids = set()
            exclusions_payload = req.exclusions or []
            for exc in exclusions_payload:
                client_exclusion_ids.add(exc.id)
                cur.execute(
                    "SELECT updated_at, is_deleted FROM activity_exclusions WHERE id = %s AND user_id = %s",
                    (exc.id, user_id)
                )
                row = cur.fetchone()
                if not row:
                    cur.execute(
                        """INSERT INTO activity_exclusions (id, user_id, activity_id, data, updated_at, is_deleted)
                           VALUES (%s, %s, %s, %s, %s, %s)""",
                        (exc.id, user_id, exc.activity_id, exc.data, exc.updated_at, exc.is_deleted)
                    )
                else:
                    db_updated_at, db_is_deleted = row[0], row[1]
                    if exc.updated_at > db_updated_at:
                        cur.execute(
                            """UPDATE activity_exclusions SET activity_id=%s, data=%s, updated_at=%s, is_deleted=%s
                               WHERE id=%s AND user_id=%s""",
                            (exc.activity_id, exc.data, exc.updated_at, exc.is_deleted, exc.id, user_id)
                        )

            # 4. Obter alterações do banco para o Cliente (novidades desde a última data de sync do cliente)
            # Buscar favoritos atualizados
            query_fav = """
                SELECT id, type, book_slug, book_title, chapter_id, chapter_name, paragraph_number, 
                       paragraph_text, timestamp, group_id, group_range, updated_at, is_deleted
                FROM favorites 
                WHERE user_id = %s AND updated_at > %s
            """
            cur.execute(query_fav, (user_id, req.last_sync_timestamp))
            db_favorites = cur.fetchall()
            
            server_favorites = []
            for row in db_favorites:
                if row[0] not in client_fav_ids:
                    server_favorites.append({
                        "id": row[0],
                        "type": row[1],
                        "book_slug": row[2],
                        "book_title": row[3],
                        "chapter_id": row[4],
                        "chapter_name": row[5],
                        "paragraph_number": row[6],
                        "paragraph_text": row[7],
                        "timestamp": int(row[8]),
                        "group_id": row[9],
                        "group_range": row[10],
                        "updated_at": int(row[11]),
                        "is_deleted": bool(row[12])
                    })

            # Buscar grifos atualizados
            query_hl = """
                SELECT id, type, book_slug, chapter_id, paragraph_number, start_word_index, 
                       end_word_index, highlighted_text, color, timestamp, end_paragraph_number, 
                       end_word_index_end, updated_at, is_deleted
                FROM highlights 
                WHERE user_id = %s AND updated_at > %s
            """
            cur.execute(query_hl, (user_id, req.last_sync_timestamp))
            db_highlights = cur.fetchall()
            
            server_highlights = []
            for row in db_highlights:
                if row[0] not in client_hl_ids:
                    server_highlights.append({
                        "id": row[0],
                        "type": row[1],
                        "book_slug": row[2],
                        "chapter_id": row[3],
                        "paragraph_number": row[4],
                        "start_word_index": row[5],
                        "end_word_index": row[6],
                        "highlighted_text": row[7],
                        "color": row[8],
                        "timestamp": int(row[9]),
                        "end_paragraph_number": row[10],
                        "end_word_index_end": row[11],
                        "updated_at": int(row[12]),
                        "is_deleted": bool(row[13])
                    })

            # Buscar chats atualizados
            query_chat = """
                SELECT id, title, created_at, updated_at, messages_json, is_deleted
                FROM chats 
                WHERE user_id = %s AND updated_at > %s
            """
            cur.execute(query_chat, (user_id, req.last_sync_timestamp))
            db_chats = cur.fetchall()
            
            server_chats = []
            for row in db_chats:
                if row[0] not in client_chat_ids:
                    server_chats.append({
                        "id": row[0],
                        "title": row[1],
                        "created_at": int(row[2]),
                        "updated_at": int(row[3]),
                        "messages_json": row[4],
                        "is_deleted": bool(row[5])
                    })

            # Buscar atividades atualizadas
            query_act = """
                SELECT id, titulo, dia, horario, lembrete_ativo, lembrete_minutos_antes, 
                       repetir, frequencia, dias_semana, cor, mensagem_lembrete, terminar_tipo, 
                       terminar_vezes, terminar_data, icone, updated_at, is_deleted
                FROM activities 
                WHERE user_id = %s AND updated_at > %s
            """
            cur.execute(query_act, (user_id, req.last_sync_timestamp))
            db_activities = cur.fetchall()
            
            server_activities = []
            for row in db_activities:
                if row[0] not in client_activity_ids:
                    server_activities.append({
                        "id": row[0],
                        "titulo": row[1],
                        "dia": row[2],
                        "horario": row[3],
                        "lembrete_ativo": bool(row[4]),
                        "lembrete_minutos_antes": int(row[5]),
                        "repetir": bool(row[6]),
                        "frequencia": row[7],
                        "dias_semana": row[8],
                        "cor": row[9],
                        "mensagem_lembrete": row[10],
                        "terminar_tipo": row[11],
                        "terminar_vezes": int(row[12]),
                        "terminar_data": row[13],
                        "icone": row[14],
                        "updated_at": int(row[15]),
                        "is_deleted": bool(row[16])
                    })

            # Buscar conclusões atualizadas
            query_comp = """
                SELECT id, activity_id, data, updated_at, is_deleted
                FROM activity_completions 
                WHERE user_id = %s AND updated_at > %s
            """
            cur.execute(query_comp, (user_id, req.last_sync_timestamp))
            db_completions = cur.fetchall()
            
            server_completions = []
            for row in db_completions:
                if row[0] not in client_completion_ids:
                    server_completions.append({
                        "id": row[0],
                        "activity_id": row[1],
                        "data": row[2],
                        "updated_at": int(row[3]),
                        "is_deleted": bool(row[4])
                    })

            # Buscar exclusões atualizadas
            query_exc = """
                SELECT id, activity_id, data, updated_at, is_deleted
                FROM activity_exclusions 
                WHERE user_id = %s AND updated_at > %s
            """
            cur.execute(query_exc, (user_id, req.last_sync_timestamp))
            db_exclusions = cur.fetchall()
            
            server_exclusions = []
            for row in db_exclusions:
                if row[0] not in client_exclusion_ids:
                    server_exclusions.append({
                        "id": row[0],
                        "activity_id": row[1],
                        "data": row[2],
                        "updated_at": int(row[3]),
                        "is_deleted": bool(row[4])
                    })

            return {
                "server_timestamp": server_timestamp,
                "changes": {
                    "favorites": server_favorites,
                    "highlights": server_highlights,
                    "chats": server_chats,
                    "activities": server_activities,
                    "completions": server_completions,
                    "exclusions": server_exclusions
                }
            }
    except Exception as e:
        logger.error(f"[Sync Endpoint] Erro durante sincronização: {e}")
        raise HTTPException(status_code=500, detail="Erro interno ao sincronizar os dados.")
