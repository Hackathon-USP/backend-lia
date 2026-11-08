"""Textos fixos do totem. O front os entrega ao VLibras e ao speechSynthesis."""

TEXTOS: dict[str, str] = {
    "boas_vindas": "Olá! Bem-vindo. Vou ajudar você a pegar sua senha de atendimento.",
    "escolher_modo": "Como você prefere se comunicar? Libras, voz ou toque na tela.",
    "consentimento": (
        "Para continuar, vamos guardar algumas informações sobre o motivo da sua vinda, "
        "além do seu nome e CPF, só para a equipe de saúde atender você. Não gravamos vídeo nem áudio. "
        "Você concorda?"
    ),
    "consentimento_recusado": (
        "Tudo bem. Procure a recepção para ser atendido pessoalmente."
    ),
    "identificacao": "Agora digite seu nome completo e seu CPF na tela.",
    "repetir": "Não entendi. Pode repetir ou tocar na opção na tela?",
    "finalizado": "Pronto! Sua senha é {senha}. Aguarde ser chamado.",
    "finalizado_preferencial": (
        "Pronto! Sua senha é {senha}, de atendimento prioritário. Aguarde ser chamado."
    ),
}
