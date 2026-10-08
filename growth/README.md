# Agente de Growth — funnel de adquisición

Analiza el funnel de adquisición de punta a punta, general y desagregado por
canal, sobre los datos reales de Bitrix24.

**Dashboard (Monitor de Growth):** https://claude.ai/artifact/3G7z5oWCzP6hjALXubjU1Y

**Viajes Comerciales:** https://claude.ai/artifact/Q1gm2Y9fjM2VcJtLyeUeYP — `python3 run.py viajes`.
Visitas de la planilla en `data/viajes.csv`; destinos en `data/viajes_destinos.json`: estado del viaje, pauta (ARS, pasada a USD con el TC de `config/definitions.yaml`) y gastos del viaje en USD por concepto (pasajes, alojamiento, viáticos).
La agenda la carga SDR en el artefacto (base compartida, colección `agenda`); para sumar sus IDs al CRM se copia a `data/viajes_agenda.json` y se vuelve a correr.
Lo hace solo la rutina diaria "Viajes Comerciales · actualización diaria" (8:50, hora de Argentina): trae la agenda, consulta el CRM (`run.py viajes-datos`) y escribe los datos en el documento `sistema/crm` de la base del artefacto. **No republica la página**: el panel lo edita todo el equipo y la página lee los datos de la base al abrir. `run.py viajes` (página completa) se usa solo al cambiar el código de `growth/plantilla_viajes.html`, partiendo siempre de la versión publicada.

## Uso

```bash
python3 run.py daily                # ingesta + dashboard + anomalías
python3 run.py report --mes 2026-08 # el funnel de un mes en consola
python3 run.py alerts               # solo los desvíos
python3 run.py alarma               # la alarma diaria (calla si no hay nada o avisa si un número del Monitor pasó a rojo)
python3 run.py semanal --url <link> # el informe semanal (dado de baja como rutina el 30/09/2026)
```

Requiere `BITRIX_WEBHOOK_URL` en el entorno (webhook entrante de Bitrix24 con
lectura de CRM). No se versiona.

## Cómo está armado

```
config/definitions.yaml   todas las definiciones del negocio en un solo lugar
growth/ingest.py          snapshot diario del crudo -> data/snapshots/
growth/metrics.py         el funnel, general y por canal
growth/health.py          cuánto hay que creerle a los números
growth/anomalies.py       desvíos con umbral, cada uno sobre su ventana
growth/alerts.py          la alarma diaria y el informe semanal
growth/slack.py           redacción de los mensajes
growth/monitor.py         los números del Monitor de Growth, un trimestre por vez
growth/dashboard.py       arma dashboard/index.html (Monitor de Growth: Funnel · Generación · Derivación · Ventas · Experimentos)
data/meta_spend.json      gasto diario de Meta separado por campaña (API, no SPA)
experiments/              registro de experimentos (solapa Experimentos del Monitor, desde el Q4 2026)
```

La ingesta guarda el crudo y el cálculo se hace después. Bitrix muestra
siempre el estado de hoy: sin snapshot no hay forma de reconstruir cómo se
veía el funnel la semana pasada. Cambiar una definición en el YAML recalcula
todo el histórico sin volver a consultar el CRM.

## Métricas

- **CPL** — inversión ÷ prospectos generados
- **CAC** — inversión ÷ clientes nuevos
- **% de derivación** — derivados ÷ prospectos del período
- **% de conversión** — cierres ÷ prospectos del período

Y además, porque el CPL solo no alcanza para decidir: costo por derivado,
costo por presupuesto, % entre etapas, MRR cerrado y presupuestado, ticket
promedio, velocidad del funnel y motivos de caída.

## Estado

| | |
|---|---|
| Meta Ads | conectado, en vivo |
| Redes Sociales | campaña `JY \| Awareness`, separada de Meta a nivel campaña |
| Google Ads | pendiente — no hay conector; entra por carga manual |
| Prospectos, negociaciones, inversión | Bitrix24, en vivo |
| Notificación a Slack | #adqui-notificaciones-canales, solo la rutina diaria (el informe semanal está dado de baja) |
| Embajadores, viajantes, cursos y webinars | mapeados, sin inversión cargada |
