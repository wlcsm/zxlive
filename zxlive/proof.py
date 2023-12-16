import json
from typing import NamedTuple, Union, Any

from PySide6.QtCore import (QAbstractListModel, QModelIndex, QPersistentModelIndex,
                            Qt, QAbstractItemModel)
from PySide6.QtGui import QFont
from pyzx.graph import GraphDiff

from .common import GraphT


class Rewrite(NamedTuple):
    """A rewrite turns a graph into another graph."""

    display_name: str # Name of proof displayed to user
    rule: str  # Name of the rule that was applied to get to this step
    graph: GraphT  # Diff from the last step to this step

    def to_json(self, graph: GraphT) -> str:
        """Serializes the rewrite to JSON."""

        print("graph", graph)
        return json.dumps({
            "display_name": self.display_name,
            "rule": self.rule,
            "diff": GraphDiff(graph, self.graph).to_json()
        })

    @staticmethod
    def from_json(json_str: str, graph: GraphT) -> "Rewrite":
        """Deserializes the rewrite from JSON."""
        d = json.loads(json_str)
        diff = GraphDiff.from_json(d["diff"])
        graph = diff.apply_diff(graph)

        return Rewrite(
            display_name=d.get("display_name", d["rule"]), # Old proofs may not have display names
            rule=d["rule"],
            graph=graph,
        )

class ProofModel(QAbstractListModel):
    """List model capturing the individual steps in a proof.

    There is a row for each graph in the proof sequence. Furthermore, we store the
    rewrite that was used to go from one graph to next.
    """

    initial_graph: GraphT
    steps: list[Rewrite]

    def __init__(self, start_graph: GraphT):
        super().__init__()
        self.initial_graph = start_graph
        self.steps = []

    def set_graph(self, index: int, graph: GraphT):
        if index == 0:
            self.initial_graph = graph
        else:
            old_step = self.steps[index-1]
            new_step = Rewrite(old_step.name, old_step.rule, graph)
            self.steps[index-1] = new_step

    def graphs(self) -> [GraphT]:
        return [self.initial_graph] + [step.graph for step in self.steps]

    def data(self, index: Union[QModelIndex, QPersistentModelIndex], role: int=Qt.ItemDataRole.DisplayRole) -> Any:
        """Overrides `QAbstractItemModel.data` to populate a view with rewrite steps"""

        if index.row() >= len(self.steps)+1 or index.column() >= 1:
            return None

        if role == Qt.ItemDataRole.DisplayRole:
            if index.row() == 0:
                return "START"
            else:
                return self.steps[index.row()-1].display_name
        elif role == Qt.ItemDataRole.FontRole:
            return QFont("monospace", 12)

    def headerData(self, section: int, orientation: Qt.Orientation,
                   role: int = Qt.ItemDataRole.DisplayRole) -> Any:
        """Overrides `QAbstractItemModel.headerData`.

        Indicates that this model doesn't have a header.
        """
        return None

    def columnCount(self, index: Union[QModelIndex, QPersistentModelIndex] = QModelIndex()) -> int:
        """The number of columns"""
        return 1

    def rowCount(self, index: Union[QModelIndex, QPersistentModelIndex] = QModelIndex()) -> int:
        """The number of rows"""
        # This is a quirk of Qt list models: Since they are based on tree models, the
        # user has to specify the index of the parent. In a list, we always expect the
        # parent to be `None` or the empty `QModelIndex()`
        if not index or not index.isValid():
            return len(self.steps)+1
        else:
            return 0

    def add_rewrite(self, rewrite: Rewrite) -> None:
        """Adds a rewrite step to the model."""
        self.beginInsertRows(QModelIndex(), len(self.steps), len(self.steps))
        self.steps.append(rewrite)
        self.endInsertRows()

    def pop_rewrite(self) -> tuple[Rewrite, GraphT]:
        """Removes the latest rewrite from the model.

        Returns the rewrite and the graph that previously resulted from this rewrite.
        """
        self.beginRemoveRows(QModelIndex(), len(self.steps), len(self.steps))
        rewrite = self.steps.pop()
        self.endRemoveRows()
        return rewrite, rewrite.graph

    def get_graph(self, index: int) -> GraphT:
        """Returns the grap at a given position in the proof."""
        if index == 0:
            return self.initial_graph.copy()
        else:
            copy = self.steps[index-1].graph.copy()
            # Mypy issue: https://github.com/python/mypy/issues/11673
            assert isinstance(copy, GraphT)  # type: ignore
            return copy

    def rename_step(self, index: int, name: str):
        """Change the display name"""
        old_step = self.steps[index-1]

        # Must create a new Rewrite object instead of modifying current object
        # since Rewrite inherits NamedTuple and is hence immutable
        self.steps[index-1] = Rewrite(name, old_step.rule, old_step.diff)

        # Rerender the proof step otherwise it will display the old name until
        # the cursor moves
        modelIndex = self.createIndex(index-1, 0)
        self.dataChanged.emit(modelIndex, modelIndex, [])

    def to_json(self) -> str:
        """Serializes the model to JSON."""
        proof_steps = []
        prev_graph = self.initial_graph.copy()
        for step in self.steps:
            proof_steps.append(step.to_json(prev_graph))
            print("prev", prev_graph.graph)
            print("new", step.graph.graph)
            prev_graph = step.graph.copy()

        return json.dumps({
            "initial_graph": self.initial_graph.to_json(),
            "proof_steps": proof_steps
        })

    @staticmethod
    def from_json(json_str: str) -> "ProofModel":
        """Deserializes the model from JSON."""
        d = json.loads(json_str)
        initial_graph = GraphT.from_json(d["initial_graph"])
        # Mypy issue: https://github.com/python/mypy/issues/11673
        assert isinstance(initial_graph, GraphT)  # type: ignore

        model = ProofModel(initial_graph)
        prev_graph = initial_graph.copy()
        for step in d["proof_steps"]:
            rewrite = Rewrite.from_json(step, prev_graph)
            model.add_rewrite(rewrite)
            prev_graph = rewrite.graph.copy()

        return model
