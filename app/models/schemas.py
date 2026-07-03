from pydantic import BaseModel
from typing import List, Optional

class RegisterRequest(BaseModel):
    nome: str
    email: str
    password: str

class LoginRequest(BaseModel):
    email: str
    password: str

class FavoriteChangeItem(BaseModel):
    id: str
    type: str
    book_slug: str
    book_title: Optional[str] = None
    chapter_id: Optional[int] = None
    chapter_name: Optional[str] = None
    paragraph_number: int
    paragraph_text: str
    timestamp: int
    group_id: Optional[str] = None
    group_range: Optional[str] = None
    updated_at: int
    is_deleted: bool

class HighlightChangeItem(BaseModel):
    id: str
    type: str
    book_slug: str
    chapter_id: int
    paragraph_number: int
    start_word_index: int
    end_word_index: int
    highlighted_text: str
    color: str
    timestamp: int
    end_paragraph_number: Optional[int] = None
    end_word_index_end: Optional[int] = None
    updated_at: int
    is_deleted: bool

class ChatChangeItem(BaseModel):
    id: str
    title: str
    created_at: int
    updated_at: int
    messages_json: str
    is_deleted: bool

class ActivityChangeItem(BaseModel):
    id: str
    titulo: str
    dia: Optional[str] = None
    horario: str
    lembrete_ativo: bool
    lembrete_minutos_antes: int
    repetir: bool
    frequencia: Optional[str] = None
    dias_semana: Optional[str] = None
    cor: str
    mensagem_lembrete: Optional[str] = None
    terminar_tipo: Optional[str] = 'nunca'
    terminar_vezes: Optional[int] = 0
    terminar_data: Optional[str] = None
    icone: Optional[str] = None
    updated_at: int
    is_deleted: bool

class ActivityCompletionChangeItem(BaseModel):
    id: str
    activity_id: str
    data: str
    updated_at: int
    is_deleted: bool

class ActivityExclusionChangeItem(BaseModel):
    id: str
    activity_id: str
    data: str
    updated_at: int
    is_deleted: bool

class SyncRequest(BaseModel):
    last_sync_timestamp: int
    favorites: List[FavoriteChangeItem]
    highlights: List[HighlightChangeItem]
    chats: Optional[List[ChatChangeItem]] = []
    activities: Optional[List[ActivityChangeItem]] = []
    completions: Optional[List[ActivityCompletionChangeItem]] = []
    exclusions: Optional[List[ActivityExclusionChangeItem]] = []

class UpdateEmailRequest(BaseModel):
    new_email: str

class UpdatePasswordRequest(BaseModel):
    current_password: str
    new_password: str

class ForgotPasswordRequest(BaseModel):
    email: str

class ResetPasswordRequest(BaseModel):
    email: str
    token: str
    new_password: str
