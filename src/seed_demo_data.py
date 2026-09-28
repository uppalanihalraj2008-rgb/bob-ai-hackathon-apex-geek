"""Loads sample_data/*.json into the database so the Streamlit demo and MCP
server have something to show immediately.

All names, injuries, and cases in sample_data/ are entirely fictional --
invented for this demo only, set in a made-up "Riverside Flood Response"
training scenario. They are not based on any real person, case, or
disaster event.

Run with:
    python seed_demo_data.py
"""
import json
import os

import database as db
from models import AnteMortemProfile, PostMortemObservation

HERE = os.path.dirname(__file__)


def main():
    db.init_db()

    with open(os.path.join(HERE, "sample_data", "ante_mortem_samples.json")) as f:
        for rec in json.load(f):
            db.add_ante_mortem(AnteMortemProfile.new(**rec))

    with open(os.path.join(HERE, "sample_data", "post_mortem_samples.json")) as f:
        for rec in json.load(f):
            db.add_post_mortem(PostMortemObservation.new(**rec))

    print(
        f"Seeded {len(db.list_ante_mortem())} ante-mortem profiles and "
        f"{len(db.list_post_mortem())} post-mortem cases into {db.DB_PATH}"
    )


if __name__ == "__main__":
    main()