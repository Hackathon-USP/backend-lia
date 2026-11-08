from enum import Enum


class TipoSenha(str, Enum):
    normal = "normal"
    preferencial = "preferencial"


class StatusSenha(str, Enum):
    aguardando = "aguardando"
    em_atendimento = "em_atendimento"
    finalizada = "finalizada"


class ModoAcessibilidade(str, Enum):
    libras = "libras"
    voz = "voz"
    toque = "toque"


class StatusAtendimento(str, Enum):
    em_andamento = "em_andamento"
    finalizado = "finalizado"
