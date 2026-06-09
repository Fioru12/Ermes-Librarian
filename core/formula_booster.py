import re

from llama_index.core.postprocessor.types import BaseNodePostprocessor
from llama_index.core.schema import NodeWithScore, QueryBundle


class FormulaNumberBooster(BaseNodePostprocessor):
    """
    Post-processor che rileva numeri di formula nella query
    (es. "formula 210", "#130") e sposta in cima i documenti
    il cui anchor name corrisponde esattamente.
    """

    _callback_manager = None

    @property
    def callback_manager(self):
        return self._callback_manager

    @callback_manager.setter
    def callback_manager(self, value):
        self._callback_manager = value

    def _postprocess_nodes(
        self,
        nodes: list[NodeWithScore],
        query_bundle: QueryBundle | None = None,
    ) -> list[NodeWithScore]:
        if query_bundle is None:
            return nodes

        query = query_bundle.query_str
        num = self._extract_formula_number(query)
        if num is None:
            return nodes

        # Cerca nodo con anchor name = num
        anchor = re.compile(r'<a\s+name="' + re.escape(num) + r'"></a>')
        boosted = []
        rest = []
        for n in nodes:
            text = n.node.get_text()
            if anchor.search(text):
                # Aumenta lo score artificialmente
                n.score = 1.0 + (n.score or 0.0)
                boosted.append(n)
            else:
                rest.append(n)

        if not boosted:
            return nodes  # nessun match

        # Ordina: boosted in cima ordinati per score, poi il resto
        boosted.sort(key=lambda x: x.score or 0.0, reverse=True)
        rest.sort(key=lambda x: x.score or 0.0, reverse=True)
        return boosted + rest

    @staticmethod
    def _extract_formula_number(query: str) -> str | None:
        # Cerca pattern come: "formula 210", "#140", "210 maggiorazioni"
        m = re.search(r'(?:formula\s*)?#?(\d{2,4})(?:\s|$|\.|,|;)', query, re.IGNORECASE)
        if m:
            return m.group(1)
        return None
