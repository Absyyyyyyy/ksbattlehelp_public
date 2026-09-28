# KingShot Battle Helper

PvP battle simulator for the mobile game **KingShot**, by Absy.

Live: [absy-simulator.streamlit.app](https://absy-simulator.streamlit.app/)

Support the project: [ko-fi.com/absyy](https://ko-fi.com/absyy)

- **Benchmark**: rank your heroes per scenario and plan upgrades with your shard budget
- **Attack & Defense**: best rally against a garrison, best garrison against a rally
- **Quick Fight**: one matchup, round by round
- **Sensitivity**: sweep one parameter and chart the outcome
- **SkillMod**: compare the skill multipliers of two lineups

## Run locally

```bash
pip install -r requirements.txt
streamlit run run_app.py
```

Screenshot import needs the Tesseract binary (`apt install tesseract-ocr`).

## Tests

```bash
pip install -r requirements-dev.txt
pytest tests/ -q
```

## Credits

Combat engine derived from State of Survival (same studio) via
[request-laurent/sos.battle](https://github.com/request-laurent/sos.battle).
Hero data: [kingshotdata.com](https://kingshotdata.com).
Community: [Discord](https://discord.gg/pwGvB99WN3) ·
[Ko-fi](https://ko-fi.com/absyy).

## License

MIT
