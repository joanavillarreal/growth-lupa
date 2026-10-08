# growth-lupa

Acá vive **Lupa**, la analista del equipo de Growth de Boxer Gestión. Todos los días trae los
números del funnel y de Meta Ads, y los lunes los de redes; actualiza los paneles y deja un
parte en `partes/` para los agentes que siguen. Mide y alerta: no propone ni ejecuta cambios.

- Quién es y sus reglas: [`CLAUDE.md`](CLAUDE.md)
- Qué analiza y cuándo: [`agenda.yaml`](agenda.yaml) — sumar un análisis es agregar un bloque.
- Links de los paneles y modo (ensayo/oficial): [`paneles.yaml`](paneles.yaml)

```bash
python3 que_toca_hoy.py                      # qué toca hoy (hora de Argentina)
python3 que_toca_hoy.py --fecha 2026-10-12   # simular otro día
python3 parte.py redes ok --resumen "..." --datos datos.json
```
