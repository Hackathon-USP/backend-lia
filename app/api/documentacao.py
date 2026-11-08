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
   Depois das perguntas fixas, a **LIA (IA)** pode fazer até 3 perguntas complementares
   pensadas para o caso do paciente (ex.: dor no peito → "Você está suando frio?"). Elas
   chegam como qualquer pergunta, com `origem: "lia"`, e são respondidas do mesmo jeito.
4. `PUT /atendimentos/{id}/identificacao` `{nome, cpf}` — obrigatório antes de finalizar
   (`identificado` na resposta indica se já foi feito).
5. `GET /atendimentos/{id}/conferencia` — resumo das respostas para o paciente conferir
   (`texto` para VLibras/voz e `itens` para a tela). Se algo estiver errado,
   `DELETE /atendimentos/{id}/respostas/{pergunta_id}` volta a triagem para aquela pergunta
   (apaga ela e as seguintes) e o fluxo segue do passo 3.
6. `POST /atendimentos/{id}/finalizar` — emite a senha e devolve a mensagem final.
   Logo depois, sem atrasar a senha, sai o **relatório da triagem** para a recepção.
7. `GET /atendimentos/{id}` — estado atual, para retomar se a tela recarregar.

Modos `libras` e `voz` recebem senha **preferencial** automaticamente (Lei 10.048/2000).

### Tela da recepção (`/recepcao`)
`GET /recepcao/fila` (senhas do dia com alertas), `POST /recepcao/chamar` (próxima senha),
`GET /recepcao/atendimentos` e `GET /recepcao/atendimentos/{id}` (resumo, respostas e
`relatorio`). `POST /recepcao/atendimentos/{id}/relatorio` gera o relatório de novo.
**Ainda sem autenticação** — não usar com dados reais antes de proteger.

### IA (opcional)
Com `OPENAI_API_KEY` configurada, a LIA usa o GPT da OpenAI (`IA_MODELO`, padrão `gpt-6-luna`,
o mais econômico) para as perguntas complementares e para escrever o relatório, com
raciocínio mínimo para gastar pouco (`IA_ESFORCO_PERGUNTA`, padrão `none`;
`IA_ESFORCO_RELATORIO`, padrão `low`). Só as respostas da triagem
são enviadas: **nome e CPF nunca vão para a IA**. A IA não faz diagnóstico nem
classificação de risco (é da enfermagem). Sem a chave, ou se a IA falhar ou demorar, a
triagem segue só com as perguntas fixas e o relatório é montado por regras
(`gerado_por: "regras"`).

### Treino do reconhecimento de Libras (`/libras`)
A página `/treinar` do front faz o avatar do VLibras sinalizar cada glosa, extrai os
pontos das mãos e do tronco e envia as amostras (`POST /libras/amostras`). Os totens
baixam com `GET /libras/amostras?depois_de=<cursor>` (só o que é novo) e treinam o
reconhecimento no próprio navegador. Por padrão o servidor só aceita a fonte `vlibras`
(`FONTES_AMOSTRAS_LIBRAS`): gravações de pessoas são dados pessoais.
"""

TAGS = [
    {"name": "conteudo", "description": "Textos e perguntas fixas, pré-carregadas pelo front."},
    {"name": "atendimentos", "description": "Sessão de triagem do paciente, da abertura à senha."},
    {"name": "senhas", "description": "Emissão e consulta de senhas da fila."},
    {"name": "recepcao", "description": "Fila do dia, detalhe dos atendimentos e chamada de senhas."},
    {"name": "libras", "description": "Amostras para treinar o reconhecimento de sinais (avatar do VLibras)."},
    {"name": "infra", "description": "Verificação de saúde do serviço."},
]
