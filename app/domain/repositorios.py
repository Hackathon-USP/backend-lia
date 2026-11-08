"""Contratos de persistência que o domínio e os casos de uso esperam.

A camada `persistence` implementa estes protocolos. Os casos de uso dependem só
deles, então trocar o banco (ou usar um repositório em memória nos testes) não
mexe em regra de negócio.
"""

from datetime import date
from typing import Protocol

from app.domain.amostras_libras import AmostraLibras
from app.domain.entidades import Atendimento, Identificacao, PerguntasDaLia, Queixa, RelatorioTriagem, Senha
from app.domain.enums import ModoAcessibilidade, StatusAtendimento, StatusSenha, TipoSenha


class RepositorioSenhas(Protocol):
    def proximo_numero(self, data_ref: date, tipo: TipoSenha) -> int:
        """Incrementa o contador do dia/tipo de forma atômica (sem duplicar entre totens)."""

    def adicionar(self, senha: Senha) -> Senha: ...

    def salvar(self, senha: Senha) -> Senha: ...

    def obter(self, senha_id: int) -> Senha | None: ...

    def buscar_do_dia(self, codigo: str, data_ref: date) -> Senha | None: ...

    def listar_do_dia(self, data_ref: date, status: StatusSenha | None = None) -> list[Senha]: ...

    def por_ids(self, senha_ids: list[int]) -> dict[int, Senha]: ...

    def tirar_da_espera(self, senha: Senha, novo_status: StatusSenha) -> bool:
        """Muda o status só se a senha ainda estiver aguardando. False se outro guichê chegou antes."""


class RepositorioAtendimentos(Protocol):
    def adicionar(self, atendimento: Atendimento) -> Atendimento: ...

    def salvar(self, atendimento: Atendimento) -> Atendimento: ...

    def obter(self, atendimento_id: int) -> Atendimento | None: ...

    def por_senhas(self, senha_ids: list[int]) -> dict[int, Atendimento]:
        """{senha_id: atendimento} das senhas que vieram de uma triagem."""

    def listar(
        self,
        status: StatusAtendimento | None = None,
        modo: ModoAcessibilidade | None = None,
        cpf: str | None = None,
    ) -> list[Atendimento]:
        """Mais recentes primeiro. `cpf` só com dígitos."""


class RepositorioIdentificacoes(Protocol):
    def obter(self, atendimento_id: int) -> Identificacao | None: ...

    def salvar(self, identificacao: Identificacao) -> Identificacao:
        """Insere ou substitui a identificação do atendimento."""

    def por_atendimentos(self, atendimento_ids: list[int]) -> dict[int, Identificacao]: ...


class RepositorioQueixas(Protocol):
    def adicionar(self, queixa: Queixa) -> Queixa: ...

    def do_atendimento(self, atendimento_id: int) -> Queixa | None: ...


class RepositorioPerguntasDaLia(Protocol):
    def obter(self, atendimento_id: int) -> PerguntasDaLia | None: ...

    def salvar(self, perguntas: PerguntasDaLia) -> PerguntasDaLia:
        """Insere ou substitui as perguntas da LIA do atendimento."""


class RepositorioRelatorios(Protocol):
    def obter(self, atendimento_id: int) -> RelatorioTriagem | None: ...

    def salvar(self, relatorio: RelatorioTriagem) -> RelatorioTriagem:
        """Insere ou substitui o relatório do atendimento."""


class RepositorioAmostrasLibras(Protocol):
    def ids_existentes(self, ids: list[str]) -> set[str]:
        """Quais destes ids já estão gravados."""

    def adicionar(self, amostra: AmostraLibras) -> AmostraLibras: ...

    def listar(
        self,
        fonte: str | None = None,
        glosa: str | None = None,
        depois_de: int = 0,
        limite: int = 100,
    ) -> list[AmostraLibras]:
        """Em ordem de chegada (`seq`), só as com `seq` > `depois_de`."""

    def contagens(self, fonte: str | None = None) -> list[tuple[str, str, str, int]]:
        """(glosa, fonte, sinalizante, quantidade) de cada combinação gravada."""

    def remover(self, fonte: str | None = None, glosa: str | None = None) -> int:
        """Apaga as que casam com os filtros e devolve quantas foram apagadas."""


class UnidadeDeTrabalho(Protocol):
    """Agrupa os repositórios de uma transação. Nada fica gravado até `commit()`."""

    senhas: RepositorioSenhas
    atendimentos: RepositorioAtendimentos
    identificacoes: RepositorioIdentificacoes
    queixas: RepositorioQueixas
    perguntas_da_lia: RepositorioPerguntasDaLia
    relatorios: RepositorioRelatorios
    amostras_libras: RepositorioAmostrasLibras

    def commit(self) -> None: ...
