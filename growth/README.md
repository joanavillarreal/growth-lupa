# Agente de Growth — funnel de adquisición

Analiza el funnel de adquisición de punta a punta, general y desagregado por
canal, sobre los datos reales de Bitrix24.

> Copiado de `agente-growth` (commit 1953e30), sin Viajes Comerciales (que sigue allá).
> En Lupa el link del Monitor sale de `paneles.yaml` según el `modo` (ensayo u oficial).


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
