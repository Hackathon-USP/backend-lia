from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Configurações lidas de variáveis de ambiente ou do arquivo .env."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "sqlite:///./totem.db"
    # Fuso usado para decidir "o dia" da senha (a numeração reinicia à meia-noite local).
    fuso_horario: str = "America/Sao_Paulo"
    # Origens liberadas para o front (separe por vírgula). "*" libera todas.
    cors_origens: str = "*"
    # Abaixo desta confiança (0 a 1) o reconhecimento de Libras/voz é descartado
    # e o totem pede para o paciente repetir.
    limiar_confianca: float = 0.7
    # IA da LIA (GPT, da OpenAI): perguntas complementares na triagem e relatório para a
    # recepção. Sem a chave (OPENAI_API_KEY), a triagem usa só as perguntas fixas e o
    # relatório sai por regras. Nome e CPF nunca são enviados à IA.
    openai_api_key: str = ""
    # O mais econômico da OpenAI (US$ 0,10 / 0,50 por milhão de tokens de entrada / saída).
    ia_modelo: str = "gpt-6-luna"
    # Raciocínio do modelo (cobrado como saída). "none" = mais barato e rápido. Os valores
    # aceitos dependem do modelo: o gpt-6-luna aceita none, low, medium, high, xhigh e max.
    ia_esforco_pergunta: str = "none"
    ia_esforco_relatorio: str = "low"
    # Fontes de amostras de Libras que o servidor aceita guardar (separe por vírgula).
    # Padrão: só o avatar do VLibras. Gravações de pessoas ("proprio") são dados pessoais
    # (LGPD) e as do V-LIBRASIL não podem ser redistribuídas: libere só com autorização.
    fontes_amostras_libras: str = "vlibras"


settings = Settings()
