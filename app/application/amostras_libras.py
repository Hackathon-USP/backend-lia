"""Casos de uso das amostras de Libras: receber do front, devolver aos totens, resumir e apagar."""

from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from app.application.relogio import agora_local
from app.domain.amostras_libras import AmostraInvalida, AmostraLibras, normalizar_glosa, validar_amostra
from app.domain.repositorios import UnidadeDeTrabalho

MAX_POR_ENVIO = 100
MAX_POR_PAGINA = 500


@dataclass
class RelatorioEnvio:
    adicionadas: int = 0
    # Já existiam (mesmo id): ficam como estavam.
    ignoradas: int = 0
    # (posição na lista enviada, motivo)
    invalidas: list[tuple[int, str]] = field(default_factory=list)


@dataclass
class PaginaAmostras:
    amostras: list[AmostraLibras]
    # Maior `seq` devolvido: o próximo pedido usa `depois_de=cursor` para continuar.
    cursor: int
    tem_mais: bool


@dataclass
class ResumoAmostras:
    total: int
    por_glosa: dict[str, int]
    por_fonte: dict[str, int]
    por_sinalizante: dict[str, int]


class ServicoAmostrasLibras:
    def __init__(self, uow: UnidadeDeTrabalho, fontes_aceitas: frozenset[str]):
        self.uow = uow
        self.fontes_aceitas = fontes_aceitas

    def enviar(self, brutas: list[Any], agora: datetime | None = None) -> RelatorioEnvio:
        """Valida e guarda as amostras. Uma amostra ruim não impede as outras de entrar."""
        if len(brutas) > MAX_POR_ENVIO:
            raise AmostraInvalida(f"Envie no máximo {MAX_POR_ENVIO} amostras por vez")
        agora = agora or agora_local()
        relatorio = RelatorioEnvio()
        validas: list[AmostraLibras] = []
        for indice, bruta in enumerate(brutas):
            try:
                validas.append(validar_amostra(bruta, self.fontes_aceitas, agora))
            except AmostraInvalida as erro:
                relatorio.invalidas.append((indice, str(erro)))

        vistas = self.uow.amostras_libras.ids_existentes([a.id for a in validas])
        for amostra in validas:
            if amostra.id in vistas:
                relatorio.ignoradas += 1
                continue
            vistas.add(amostra.id)
            self.uow.amostras_libras.adicionar(amostra)
            relatorio.adicionadas += 1
        self.uow.commit()
        return relatorio

    def listar(
        self,
        fonte: str | None = None,
        glosa: str | None = None,
        depois_de: int = 0,
        limite: int = 100,
    ) -> PaginaAmostras:
        limite = max(1, min(limite, MAX_POR_PAGINA))
        glosa = normalizar_glosa(glosa) if glosa else None
        # Pede uma a mais só para saber se ainda há outra página.
        amostras = self.uow.amostras_libras.listar(fonte, glosa, depois_de, limite + 1)
        tem_mais = len(amostras) > limite
        amostras = amostras[:limite]
        cursor = amostras[-1].seq if amostras else depois_de
        return PaginaAmostras(amostras, cursor, tem_mais)

    def resumir(self, fonte: str | None = None) -> ResumoAmostras:
        por_glosa: Counter[str] = Counter()
        por_fonte: Counter[str] = Counter()
        por_sinalizante: Counter[str] = Counter()
        for glosa, fonte_amostra, sinalizante, quantidade in self.uow.amostras_libras.contagens(fonte):
            por_glosa[glosa] += quantidade
            por_fonte[fonte_amostra] += quantidade
            por_sinalizante[sinalizante] += quantidade
        return ResumoAmostras(
            total=sum(por_fonte.values()),
            por_glosa=dict(sorted(por_glosa.items())),
            por_fonte=dict(por_fonte),
            por_sinalizante=dict(sorted(por_sinalizante.items())),
        )

    def remover(self, fonte: str | None = None, glosa: str | None = None) -> int:
        """Apaga do servidor (os totens que já baixaram continuam com as suas cópias)."""
        if not fonte and not glosa:
            raise AmostraInvalida("Informe a fonte ou a glosa das amostras que quer apagar")
        removidas = self.uow.amostras_libras.remover(fonte or None, normalizar_glosa(glosa) if glosa else None)
        self.uow.commit()
        return removidas
