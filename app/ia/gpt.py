"""A LIA com o GPT (OpenAI): implementa `app.domain.assistente.AssistenteTriagem`.

- Modelo padrão `gpt-6-luna`: o mais econômico da OpenAI para tarefas focadas e de
  alto volume (US$ 0,10 por milhão de tokens de entrada e US$ 0,50 de saída).
- Saída estruturada (JSON validado pelo Pydantic), então a triagem nunca recebe texto solto.
- Raciocínio mínimo para gastar pouco (os tokens de raciocínio são cobrados como saída):
  nenhum na pergunta complementar, baixo no relatório. Dá para mudar por configuração.
- Pergunta complementar: sem novas tentativas e prazo curto, porque o paciente está
  esperando na frente do totem. Relatório: mais tempo, porque é gerado depois que o
  paciente já recebeu a senha.
- `store=False`: as respostas da triagem não ficam guardadas na OpenAI.
- Qualquer falha vira `AssistenteIndisponivel`; quem chama segue sem a IA.
"""

import logging
from typing import TypeVar

import openai
from pydantic import BaseModel

from app.domain.assistente import AssistenteIndisponivel
from app.domain.perguntas_da_lia import OpcaoSugerida, PerguntaSugerida
from app.domain.relatorio import ConteudoRelatorio, ContextoTriagem
from app.ia.prompts import SISTEMA_PERGUNTA, SISTEMA_RELATORIO, descrever_contexto

logger = logging.getLogger(__name__)

MODELO_PADRAO = "gpt-6-luna"
# Valores aceitos dependem do modelo (gpt-6-luna: none, low, medium, high, xhigh, max).
ESFORCO_PERGUNTA_PADRAO = "none"
ESFORCO_RELATORIO_PADRAO = "low"

Formato = TypeVar("Formato", bound=BaseModel)


# --- Formatos de resposta pedidos ao modelo ------------------------------------


class _Opcao(BaseModel):
    rotulo: str
    alerta: str | None


class _Pergunta(BaseModel):
    texto: str
    titulo: str
    opcoes: list[_Opcao]


class _Decisao(BaseModel):
    perguntar: bool
    pergunta: _Pergunta | None


class _Relatorio(BaseModel):
    queixa_principal: str
    resumo: str
    sinais_de_alerta: list[str]
    pontos_a_confirmar: list[str]
    orientacao_recepcao: str


class AssistenteGPT:
    def __init__(
        self,
        api_key: str,
        modelo: str = MODELO_PADRAO,
        esforco_pergunta: str = ESFORCO_PERGUNTA_PADRAO,
        esforco_relatorio: str = ESFORCO_RELATORIO_PADRAO,
        tempo_pergunta_s: float = 15,
        tempo_relatorio_s: float = 90,
    ):
        self.modelo = modelo
        self.esforco_pergunta = esforco_pergunta
        self.esforco_relatorio = esforco_relatorio
        cliente = openai.OpenAI(api_key=api_key)
        # O paciente espera pela pergunta: uma tentativa só, com prazo curto.
        self._cliente_pergunta = cliente.with_options(timeout=tempo_pergunta_s, max_retries=0)
        self._cliente_relatorio = cliente.with_options(timeout=tempo_relatorio_s, max_retries=2)

    def sugerir_pergunta(self, contexto: ContextoTriagem) -> PerguntaSugerida | None:
        decisao = self._pedir(
            self._cliente_pergunta, SISTEMA_PERGUNTA, contexto, _Decisao, self.esforco_pergunta, max_tokens=2048
        )
        if not decisao.perguntar or decisao.pergunta is None:
            return None
        p = decisao.pergunta
        return PerguntaSugerida(
            texto=p.texto,
            titulo=p.titulo,
            opcoes=tuple(OpcaoSugerida(o.rotulo, o.alerta) for o in p.opcoes),
        )

    def escrever_relatorio(self, contexto: ContextoTriagem) -> ConteudoRelatorio:
        r = self._pedir(
            self._cliente_relatorio, SISTEMA_RELATORIO, contexto, _Relatorio, self.esforco_relatorio, max_tokens=4096
        )
        return ConteudoRelatorio(
            queixa_principal=r.queixa_principal,
            resumo=r.resumo,
            sinais_de_alerta=tuple(r.sinais_de_alerta),
            pontos_a_confirmar=tuple(r.pontos_a_confirmar),
            orientacao_recepcao=r.orientacao_recepcao,
        )

    def _pedir(
        self,
        cliente: openai.OpenAI,
        sistema: str,
        contexto: ContextoTriagem,
        formato: type[Formato],
        esforco: str,
        max_tokens: int,
    ) -> Formato:
        try:
            resposta = cliente.responses.parse(
                model=self.modelo,
                instructions=sistema,
                input=descrever_contexto(contexto),
                text_format=formato,
                reasoning={"effort": esforco},
                max_output_tokens=max_tokens,  # inclui os tokens de raciocínio
                store=False,
            )
        except openai.AuthenticationError as erro:
            logger.error("Chave da OpenAI inválida (OPENAI_API_KEY): %s", erro)
            raise AssistenteIndisponivel("chave da IA inválida") from erro
        except openai.RateLimitError as erro:
            raise AssistenteIndisponivel("limite de uso da IA atingido") from erro
        except openai.APIStatusError as erro:
            raise AssistenteIndisponivel(f"a IA respondeu com erro {erro.status_code}") from erro
        except openai.APIConnectionError as erro:  # inclui o tempo esgotado
            raise AssistenteIndisponivel("sem resposta da IA a tempo") from erro
        except ValueError as erro:  # JSON fora do formato pedido
            raise AssistenteIndisponivel("resposta da IA fora do formato") from erro

        # Recusa ou resposta cortada (limite de tokens, filtro de conteúdo) não trazem o JSON.
        if resposta.status != "completed" or resposta.output_parsed is None:
            motivo = resposta.incomplete_details.reason if resposta.incomplete_details else resposta.status
            raise AssistenteIndisponivel(f"resposta da IA inutilizável ({motivo})")
        return resposta.output_parsed
