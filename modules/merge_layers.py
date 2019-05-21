#! usr/bin/python_3
from pathlib import Path
from typing import List

from lxml import etree


class MergeLayerByName:
    """
        Identify layers matching the name of their DeltaGen origin target look
        and merge them with the most common source look read from DeltaGen POS variants file.

            Eg.:
            t_seat_a -> leather_black
            t_seat_b -> leather_black

            Return a appropriate mapping dict so we can merge those layer mattes together
    """
    def __init__(self, layer_names: List[str], scene_file: Path):
        self.layer_names = layer_names
        self.scene_file = Path(scene_file)
        self.pos_file = self.scene_file.with_suffix('.pos')

    def create_layer_mapping(self) -> dict:
        if not self.pos_file.exists():
            return dict()

        return self._read_xml()

    def _read_xml(self) -> dict:
        with open(self.pos_file.as_posix(), 'r') as f:
            et = etree.parse(f)

        mapping = dict()
        for e in et.iterfind('*/actionList/action[@type="appearance"]'):
            actor = e.find('actor')
            value = e.find('value')

            if actor is not None and value is not None:
                if actor.text in self.layer_names:
                    mapping[actor.text] = value.text
                    self.layer_names.remove(actor.text)

        return mapping
