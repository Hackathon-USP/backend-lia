"""Implementação SQL (SQLModel/SQLAlchemy) dos repositórios definidos em `app.domain.repositorios`.

Os repositórios só fazem `flush` (para gerar ids); quem decide o `commit` é o
caso de uso, pela unidade de trabalho.
"""

from dataclasses import fields
from datetime import date
from typing import Any, Generic, TypeVar

from sqlalchemy import delete, func, update
from sqlalchemy.dialects import postgresql, sqlite
from sqlmodel import Session, SQLModel, select

from app.domain.amostras_libras import AmostraLibras
from app.domain.entidades import Atendimento, Identificacao, Queixa, Senha
from app.domain.enums import ModoAcessibilidade, StatusAtendimento, StatusSenha, TipoSenha
from app.persistence.mapeadores import copiar_para_linha, para_entidade
from app.persistence.tabelas import (
    AmostraLibrasTabela,
    AtendimentoTabela,
    ContadorSenhaTabela,
    IdentificacaoTabela,
    QueixaTabela,
    SenhaTabela,
)

Entidade = TypeVar("Entidade")

_INSERT_POR_DIALETO = {"postgresql": postgresql.insert, "sqlite": sqlite.insert}


class _RepositorioSql(Generic[Entidade]):
    """Operações comuns: buscar por chave e gravar (insere ou atualiza) uma entidade."""

    tabela: type[SQLModel]
    entidade: type[Entidade]

    def __init__(self, session: Session):
        self.session = session

    def _para_entidade(self, linha: SQLModel | None) -> Entidade | None:
        return para_entidade(self.entidade, linha) if linha is not None else None

    def _obter(self, chave: Any) -> Entidade | None:
        return self._para_entidade(self.session.get(self.tabela, chave))

    def _gravar(self, entidade: Entidade, chave: Any) -> Entidade:
        linha = self.session.get(self.tabela, chave) if chave is not None else None
        linha = copiar_para_linha(entidade, linha or self.tabela())
        self.session.add(linha)
        self.session.flush()
        self.session.refresh(linha)
        return self._para_entidade(linha)

    def _listar(self, consulta) -> list[Entidade]:
        return [self._para_entidade(linha) for linha in self.session.exec(consulta).all()]


class RepositorioSenhasSql(_RepositorioSql[Senha]):
    tabela = SenhaTabela
    entidade = Senha

    def proximo_numero(self, data_ref: date, tipo: TipoSenha) -> int:
        """UPSERT ... RETURNING num só comando: dois totens ao mesmo tempo nunca
        recebem o mesmo número (o banco serializa o acesso à linha do contador)."""
        dialeto = self.session.get_bind().dialect.name
        if dialeto not in _INSERT_POR_DIALETO:
            raise RuntimeError(f"Banco não suportado: {dialeto}")
        insert = _INSERT_POR_DIALETO[dialeto]

        contador = ContadorSenhaTabela.__table__
        comando = (
            insert(contador)
            .values(data_ref=data_ref, tipo=tipo, valor=1)
            .on_conflict_do_update(
                index_elements=["data_ref", "tipo"],
                set_={"valor": contador.c.valor + 1},
            )
            .returning(contador.c.valor)
        )
        return self.session.connection().execute(comando).scalar_one()

    def adicionar(self, senha: Senha) -> Senha:
        return self._gravar(senha, None)

    def salvar(self, senha: Senha) -> Senha:
        return self._gravar(senha, senha.id)

    def obter(self, senha_id: int) -> Senha | None:
        return self._obter(senha_id)

    def buscar_do_dia(self, codigo: str, data_ref: date) -> Senha | None:
        consulta = select(SenhaTabela).where(SenhaTabela.codigo == codigo, SenhaTabela.data_ref == data_ref)
        return self._para_entidade(self.session.exec(consulta).first())

    def listar_do_dia(self, data_ref: date, status: StatusSenha | None = None) -> list[Senha]:
        consulta = select(SenhaTabela).where(SenhaTabela.data_ref == data_ref)
        if status is not None:
            consulta = consulta.where(SenhaTabela.status == status)
        return self._listar(consulta)

    def por_ids(self, senha_ids: list[int]) -> dict[int, Senha]:
        if not senha_ids:
            return {}
        senhas = self._listar(select(SenhaTabela).where(SenhaTabela.id.in_(senha_ids)))
        return {s.id: s for s in senhas}

    def tirar_da_espera(self, senha: Senha, novo_status: StatusSenha) -> bool:
        """UPDATE condicional: só um guichê consegue tirar a senha de `aguardando`."""
        resultado = self.session.connection().execute(
            update(SenhaTabela)
            .where(SenhaTabela.id == senha.id, SenhaTabela.status == StatusSenha.aguardando)
            .values(status=novo_status)
        )
        linha = self.session.get(SenhaTabela, senha.id)
        self.session.refresh(linha)
        senha.status = linha.status
        return resultado.rowcount == 1


class RepositorioAtendimentosSql(_RepositorioSql[Atendimento]):
    tabela = AtendimentoTabela
    entidade = Atendimento

    def adicionar(self, atendimento: Atendimento) -> Atendimento:
        return self._gravar(atendimento, None)

    def salvar(self, atendimento: Atendimento) -> Atendimento:
        return self._gravar(atendimento, atendimento.id)

    def obter(self, atendimento_id: int) -> Atendimento | None:
        return self._obter(atendimento_id)

    def por_senhas(self, senha_ids: list[int]) -> dict[int, Atendimento]:
        if not senha_ids:
            return {}
        consulta = select(AtendimentoTabela).where(AtendimentoTabela.senha_id.in_(senha_ids))
        return {a.senha_id: a for a in self._listar(consulta)}

    def listar(
        self,
        status: StatusAtendimento | None = None,
        modo: ModoAcessibilidade | None = None,
        cpf: str | None = None,
    ) -> list[Atendimento]:
        consulta = select(AtendimentoTabela)
        if cpf is not None:
            consulta = consulta.join(
                IdentificacaoTabela, IdentificacaoTabela.atendimento_id == AtendimentoTabela.id
            ).where(IdentificacaoTabela.cpf == cpf)
        if status is not None:
            consulta = consulta.where(AtendimentoTabela.status == status)
        if modo is not None:
            consulta = consulta.where(AtendimentoTabela.modo == modo)
        return self._listar(consulta.order_by(AtendimentoTabela.criado_em.desc(), AtendimentoTabela.id.desc()))


class RepositorioIdentificacoesSql(_RepositorioSql[Identificacao]):
    tabela = IdentificacaoTabela
    entidade = Identificacao

    def obter(self, atendimento_id: int) -> Identificacao | None:
        return self._obter(atendimento_id)

    def salvar(self, identificacao: Identificacao) -> Identificacao:
        return self._gravar(identificacao, identificacao.atendimento_id)

    def por_atendimentos(self, atendimento_ids: list[int]) -> dict[int, Identificacao]:
        if not atendimento_ids:
            return {}
        consulta = select(IdentificacaoTabela).where(IdentificacaoTabela.atendimento_id.in_(atendimento_ids))
        return {i.atendimento_id: i for i in self._listar(consulta)}


class RepositorioQueixasSql(_RepositorioSql[Queixa]):
    tabela = QueixaTabela
    entidade = Queixa

    def adicionar(self, queixa: Queixa) -> Queixa:
        return self._gravar(queixa, None)

    def do_atendimento(self, atendimento_id: int) -> Queixa | None:
        consulta = select(QueixaTabela).where(QueixaTabela.atendimento_id == atendimento_id)
        return self._para_entidade(self.session.exec(consulta).first())


class RepositorioAmostrasLibrasSql(_RepositorioSql[AmostraLibras]):
    tabela = AmostraLibrasTabela
    entidade = AmostraLibras

    def _para_entidade(self, linha: SQLModel | None) -> AmostraLibras | None:
        # Sem a cópia profunda do mapeador genérico: cada amostra tem ~10 mil números e as
        # linhas lidas aqui não são alteradas depois (as amostras nunca são editadas).
        if linha is None:
            return None
        return AmostraLibras(**{campo.name: getattr(linha, campo.name) for campo in fields(AmostraLibras)})

    def ids_existentes(self, ids: list[str]) -> set[str]:
        if not ids:
            return set()
        consulta = select(AmostraLibrasTabela.id).where(AmostraLibrasTabela.id.in_(ids))
        return set(self.session.exec(consulta).all())

    def adicionar(self, amostra: AmostraLibras) -> AmostraLibras:
        return self._gravar(amostra, None)

    def _filtrar(self, consulta, fonte: str | None, glosa: str | None):
        if fonte is not None:
            consulta = consulta.where(AmostraLibrasTabela.fonte == fonte)
        if glosa is not None:
            consulta = consulta.where(AmostraLibrasTabela.glosa == glosa)
        return consulta

    def listar(
        self,
        fonte: str | None = None,
        glosa: str | None = None,
        depois_de: int = 0,
        limite: int = 100,
    ) -> list[AmostraLibras]:
        consulta = self._filtrar(select(AmostraLibrasTabela), fonte, glosa)
        consulta = consulta.where(AmostraLibrasTabela.seq > depois_de)
        return self._listar(consulta.order_by(AmostraLibrasTabela.seq).limit(limite))

    def contagens(self, fonte: str | None = None) -> list[tuple[str, str, str, int]]:
        t = AmostraLibrasTabela
        consulta = self._filtrar(
            select(t.glosa, t.fonte, t.sinalizante, func.count()).group_by(t.glosa, t.fonte, t.sinalizante),
            fonte,
            None,
        )
        return [tuple(linha) for linha in self.session.exec(consulta).all()]

    def remover(self, fonte: str | None = None, glosa: str | None = None) -> int:
        comando = self._filtrar(delete(AmostraLibrasTabela), fonte, glosa)
        return self.session.connection().execute(comando).rowcount
