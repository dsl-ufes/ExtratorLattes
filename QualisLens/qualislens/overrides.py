"""Versioned manual Qualis decisions."""

import csv
from dataclasses import dataclass
from pathlib import Path
from .constants import POLITICA_VERSAO


SCHEMA_VERSAO = "1"
ACOES = {"ASSOCIAR", "SEM_CORRESPONDENCIA"}


@dataclass(frozen=True)
class Override:
    qualis_input_id: str
    acao: str
    qualis_registro_id: str
    justificativa: str
    decidido_por: str
    decidido_em: str
    politica_versao: str


class OverrideRepository:
    def __init__(self, path: str | None = None) -> None:
        self.path = path
        self._items: dict[str, Override] = {}
        if path is not None:
            self._load(Path(path))

    def _load(self, path: Path) -> None:
        if not path.is_file():
            raise FileNotFoundError(f"Arquivo de overrides Qualis não encontrado: {path}")
        with path.open(encoding="utf-8-sig", newline="") as stream:
            reader = csv.DictReader(stream)
            required = {"schema_versao", "qualis_input_id", "acao", "qualis_registro_id", "justificativa", "decidido_por", "decidido_em", "politica_versao"}
            if not reader.fieldnames or not required.issubset(reader.fieldnames):
                raise ValueError("Schema inválido de overrides Qualis")
            for row in reader:
                item = Override(**{
                    key: (row.get(key) or "").strip()
                    for key in ("qualis_input_id", "acao", "qualis_registro_id", "justificativa", "decidido_por", "decidido_em", "politica_versao")
                })
                if (row.get("schema_versao") or "").strip() != SCHEMA_VERSAO:
                    raise ValueError("Versão de schema de override inválida")
                if not item.qualis_input_id or item.acao not in ACOES:
                    raise ValueError("Override Qualis sem input ID ou ação válida")
                if item.acao == "ASSOCIAR" and not item.qualis_registro_id:
                    raise ValueError("ASSOCIAR requer qualis_registro_id")
                if item.acao == "SEM_CORRESPONDENCIA" and item.qualis_registro_id:
                    raise ValueError("SEM_CORRESPONDENCIA não aceita qualis_registro_id")
                if item.politica_versao != POLITICA_VERSAO:
                    raise ValueError("Versão de política de override inválida")
                old = self._items.get(item.qualis_input_id)
                if old and old != item:
                    raise ValueError(f"Overrides conflitantes: {item.qualis_input_id}")
                self._items[item.qualis_input_id] = item

    def get(self, qualis_input_id: str) -> Override | None:
        return self._items.get(qualis_input_id)
