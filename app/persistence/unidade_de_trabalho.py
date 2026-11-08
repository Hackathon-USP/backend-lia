from sqlmodel import Session

from app.persistence.repositorios import (
    RepositorioAtendimentosSql,
    RepositorioIdentificacoesSql,
    RepositorioPerguntasDaLiaSql,
    RepositorioQueixasSql,
    RepositorioRelatoriosSql,
    RepositorioSenhasSql,
)


class UnidadeDeTrabalhoSql:
    """Implementa `app.domain.repositorios.UnidadeDeTrabalho` sobre uma sessão do SQLModel."""

    def __init__(self, session: Session):
        self.session = session
        self.senhas = RepositorioSenhasSql(session)
        self.atendimentos = RepositorioAtendimentosSql(session)
        self.identificacoes = RepositorioIdentificacoesSql(session)
        self.queixas = RepositorioQueixasSql(session)
        self.perguntas_da_lia = RepositorioPerguntasDaLiaSql(session)
        self.relatorios = RepositorioRelatoriosSql(session)

    def commit(self) -> None:
        self.session.commit()
