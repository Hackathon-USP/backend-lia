"""Textos do OpenAPI (/docs): visão geral do fluxo e descrição das tags."""

DESCRICAO = """
API da **tela do paciente** do totem de atendimento acessível.

O front cuida de VLibras (texto → avatar em Libras), do reconhecimento de sinais
(MediaPipe) e da voz (Web Speech API). O back end guarda o atendimento, decide a
ramificação das perguntas, emite a senha e monta o resumo para a recepção.

### Fluxo da tela do paciente
1. `GET /conteudo/textos` e `GET /conteudo/perguntas` — pré-carrega textos fixos e o
   vocabulário de sinais aceito em cada opção.
2. `POST /atendimentos` `{modo, consentimento: true}` — inicia e devolve a 1ª pergunta.
3. `POST /atendimentos/{id}/respostas` `{pergunta_id, valor, canal?, confianca?}` —
   grava a resposta e devolve `proxima_pergunta` (ou `null` quando pode finalizar).
   O `valor` pode ser o id da opção, o rótulo ou o **nome do sinal** reconhecido
   (ex.: `"DOR"`). Se vier por Libras/voz com `confianca` baixa, ou com um sinal que
   não casa com nenhuma opção, nada é gravado e a resposta vem com `repetir: true`.
4. `PUT /atendimentos/{id}/identificacao` `{nome, cpf}` — obrigatório antes de finalizar
   (`identificado` na resposta indica se já foi feito).
5. `POST /atendimentos/{id}/finalizar` — emite a senha e devolve a mensagem final.
6. `GET /atendimentos/{id}` — estado atual, para retomar se a tela recarregar.

Modos `libras` e `voz` recebem senha **preferencial** automaticamente (Lei 10.048/2000).

### Tela da recepção (`/recepcao`)
`GET /recepcao/fila` (senhas do dia com alertas), `POST /recepcao/chamar` (próxima senha),
`GET /recepcao/atendimentos` e `GET /recepcao/atendimentos/{id}` (resumo e respostas).
**Ainda sem autenticação** — não usar com dados reais antes de proteger.
"""

TAGS = [
    {"name": "conteudo", "description": "Textos e perguntas fixas, pré-carregadas pelo front."},
    {"name": "atendimentos", "description": "Sessão de triagem do paciente, da abertura à senha."},
    {"name": "senhas", "description": "Emissão e consulta de senhas da fila."},
    {"name": "recepcao", "description": "Fila do dia, detalhe dos atendimentos e chamada de senhas."},
    {"name": "infra", "description": "Verificação de saúde do serviço."},
]
