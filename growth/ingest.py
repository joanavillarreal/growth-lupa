"""Ingesta desde Bitrix24 -> snapshot diario en data/snapshots/YYYY-MM-DD.json.

Guardamos el crudo, no el agregado. Bitrix muestra siempre el estado de hoy:
sin snapshot no hay forma de reconstruir cómo se veía el funnel la semana pasada,
ni de comparar contra nada. Todo el cálculo se hace después, sobre el snapshot.
"""
from __future__ import annotations
import json
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from .bitrix import Bitrix
from .config import Config, DIR_SNAPSHOTS

CAMPOS_LEAD_BASE = [
    "ID", "DATE_CREATE", "DATE_MODIFY", "DATE_CLOSED", "SOURCE_ID", "STATUS_ID",
    "ASSIGNED_BY_ID", "HAS_PHONE", "HAS_EMAIL", "TITLE", "COMPANY_TITLE",
]


def _campos_deal(cfg: Config) -> list[str]:
    f = cfg["funnel"]
    return [
        "ID", "DATE_CREATE", "SOURCE_ID", "CATEGORY_ID", "STAGE_ID",
        "OPPORTUNITY", "CURRENCY_ID", "LEAD_ID", "ASSIGNED_BY_ID", "CLOSED",
        f["derivado"]["campo_fecha_deal"],
        f["presupuestado"]["campo_fecha"],
        f["cierre"]["campo_fecha"],
    ] + [cfg["monitor"]["campos"][k] for k in ("tipo_negocio_deal", "plan_deal", "paquete_deal")]


def traer_prospectos(bx: Bitrix, cfg: Config, desde: str, hasta: str) -> list[dict]:
    campos = CAMPOS_LEAD_BASE + [cfg["funnel"]["no_derivacion"]["campo"],
                                 cfg["monitor"]["campos"]["tipo_negocio_lead"]]
    prospectos = bx.listar(
        "crm.lead.list",
        filter={">=DATE_CREATE": desde, "<=DATE_CREATE": f"{hasta}T23:59:59"},
        select=campos,
        order={"ID": "ASC"},
    )
    corregidas = {str(k): v for k, v in (cfg["funnel"]["prospecto"].get("fechas_corregidas") or {}).items()}
    for lead in prospectos:
        if lead["ID"] in corregidas:
            lead["DATE_CREATE_BITRIX"] = lead["DATE_CREATE"]
            lead["DATE_CREATE"] = corregidas[lead["ID"]]
    return prospectos


def catalogo_razones(bx: Bitrix, cfg: Config) -> dict[str, str]:
    """ID -> texto de la razón de no derivación, tal como está en Bitrix."""
    campo = bx.llamar("crm.lead.fields")["result"].get(cfg["funnel"]["no_derivacion"]["campo"], {})
    return {str(i["ID"]): i["VALUE"] for i in campo.get("items", [])}


def traer_negociaciones(bx: Bitrix, cfg: Config, desde: str, hasta: str) -> list[dict]:
    """Unión de negociaciones tocadas por el período.

    Una negociación creada el año pasado puede cerrar este mes, así que no
    alcanza con filtrar por fecha de creación: consultamos por cada hito y
    unimos por ID.
    """
    f = cfg["funnel"]
    campos = _campos_deal(cfg)
    hasta_fin = f"{hasta}T23:59:59"
    filtros = [
        {">=DATE_CREATE": desde, "<=DATE_CREATE": hasta_fin},
        {">=" + f["derivado"]["campo_fecha_deal"]: desde, "<=" + f["derivado"]["campo_fecha_deal"]: hasta_fin},
        {">=" + f["presupuestado"]["campo_fecha"]: desde, "<=" + f["presupuestado"]["campo_fecha"]: hasta_fin},
        {">=" + f["cierre"]["campo_fecha"]: desde, "<=" + f["cierre"]["campo_fecha"]: hasta_fin},
    ]
    # Las columnas "a futuro" se traen enteras: una negociación puede estar
    # estacionada ahí desde antes de la ventana y sigue siendo cartera del asesor.
    filtros.append({"STAGE_ID": list(cfg["monitor"]["etapas_a_futuro"])})
    por_id: dict[str, dict] = {}
    for filtro in filtros:
        for d in bx.listar("crm.deal.list", filter=filtro, select=campos, order={"ID": "ASC"}):
            por_id[d["ID"]] = d
    return list(por_id.values())


def catalogos_monitor(bx: Bitrix, cfg: Config) -> dict:
    """Textos de los campos lista y nombres de etapa, para no mostrar IDs."""
    c = cfg["monitor"]["campos"]
    campos_deal = bx.llamar("crm.deal.fields")["result"]
    campos_lead = bx.llamar("crm.lead.fields")["result"]

    def items(campos, clave):
        return {str(i["ID"]): i["VALUE"] for i in campos.get(clave, {}).get("items", [])}

    etapas = {}
    for cat in [{"ID": "0", "NAME": "General"}] + bx.llamar("crm.dealcategory.list")["result"]:
        for st in bx.llamar("crm.dealcategory.stage.list", id=int(cat["ID"]))["result"]:
            etapas[st["STATUS_ID"]] = f'{cat["NAME"]} · {st["NAME"]}'
    return {
        "tipo_negocio": {**items(campos_lead, c["tipo_negocio_lead"]), **items(campos_deal, c["tipo_negocio_deal"])},
        "plan": items(campos_deal, c["plan_deal"]),
        "paquete": items(campos_deal, c["paquete_deal"]),
        "etapas": etapas,
    }


def catalogo_usuarios(bx: Bitrix, ids: set[str]) -> dict[str, str]:
    """ID -> nombre de los responsables, leído del CRM.

    Necesita el permiso de usuarios (user / user_brief) en el webhook. Si no
    lo tiene, devuelve vacío y el Monitor usa los nombres de
    monitor.asesores en el YAML.
    """
    try:
        # Sin filtro de ACTIVE ya vienen también los que no están más en la empresa.
        filas = bx.listar("user.get", FILTER={"ID": sorted(ids, key=int)})
    except Exception:
        return {}
    def nombre(u):
        palabras = " ".join(x for x in (u.get("NAME"), u.get("LAST_NAME")) if x).split()
        # "Dorelia Battelini" + "Battelini": el apellido cargado dos veces.
        return " ".join(p for i, p in enumerate(palabras) if not i or p != palabras[i - 1])
    return {str(u["ID"]): nombre(u) for u in filas if u.get("ID")}


def traer_actividades(bx: Bitrix, desde: str, deals_abiertos: list[str]) -> dict:
    """Actividades del timeline, reducidas a lo que usa el monitor.

    - de prospectos: cuándo se creó cada una, para contar cuántas hubo hasta
      la derivación.
    - de negociaciones: solo las pendientes, con su vencimiento, para saber
      qué cartera a futuro no tiene nada agendado o lo tiene vencido.
    Se guardan compactas ([dueño, fecha]) porque el snapshot se versiona.
    """
    leads = bx.listar("crm.activity.list",
                      filter={"OWNER_TYPE_ID": 1, ">=CREATED": desde},
                      select=["ID", "OWNER_ID", "CREATED"], order={"ID": "ASC"})
    pendientes = bx.listar("crm.activity.list",
                           filter={"OWNER_TYPE_ID": 2, "COMPLETED": "N"},
                           select=["ID", "OWNER_ID", "DEADLINE"], order={"ID": "ASC"})
    abiertos = set(deals_abiertos)
    return {
        "prospectos": [[a["OWNER_ID"], a_hora_argentina(a.get("CREATED") or "")[:10]] for a in leads],
        "pendientes_negociacion": [[a["OWNER_ID"], a_hora_argentina(a.get("DEADLINE") or "")[:10]]
                                   for a in pendientes if a["OWNER_ID"] in abiertos],
    }


def traer_gastos(bx: Bitrix, cfg: Config, desde: str, hasta: str) -> list[dict]:
    g = cfg["gasto"]
    items = bx.listar_items(
        g["entity_type_id"],
        select=["id", "title", g["campo_tipo"], g["campo_fecha"], g["campo_monto"]],
        order={"id": "ASC"},
    )
    # El SPA es chico: filtramos por fecha en memoria y evitamos sorpresas de
    # formato en los filtros de campos de usuario.
    salida = []
    for it in items:
        fecha = (it.get(g["campo_fecha"]) or "")[:10]
        if fecha and desde <= fecha <= hasta:
            salida.append(it)
    return salida


def correr(cfg: Config | None = None, hasta: str | None = None) -> Path:
    cfg = cfg or Config()
    bx = Bitrix()
    desde = cfg["periodo"]["inicio_historico"]
    hasta = hasta or date.today().isoformat()

    negociaciones = traer_negociaciones(bx, cfg, desde, hasta)
    a_futuro = [d["ID"] for d in negociaciones if d.get("STAGE_ID") in cfg["monitor"]["etapas_a_futuro"]]
    snapshot = {
        "generado_en": datetime.now().astimezone().isoformat(timespec="seconds"),
        "ventana": {"desde": desde, "hasta": hasta},
        "catalogo_origenes": bx.catalogo_origenes(),
        "catalogo_razones": catalogo_razones(bx, cfg),
        "catalogos": catalogos_monitor(bx, cfg) | {"usuarios": catalogo_usuarios(
            bx, {str(d.get("ASSIGNED_BY_ID")) for d in negociaciones if d.get("ASSIGNED_BY_ID")})},
        "prospectos": traer_prospectos(bx, cfg, desde, hasta),
        "negociaciones": negociaciones,
        "actividades": traer_actividades(bx, desde, a_futuro),
        "gastos": traer_gastos(bx, cfg, desde, hasta),
    }

    DIR_SNAPSHOTS.mkdir(parents=True, exist_ok=True)
    destino = DIR_SNAPSHOTS / f"{hasta}.json"
    destino.write_text(json.dumps(snapshot, ensure_ascii=False, indent=1), encoding="utf-8")
    return destino


# Bitrix guarda fecha y hora en el horario de su servidor (+03:00), seis horas
# adelante de Argentina: un lead del viernes a las 20 hs figura como sábado.
# Todo el agente cuenta días y semanas en hora argentina. Los campos de solo
# fecha (derivación, presupuestado, cierre, SPA de gastos) son días puros y no
# se tocan.
ARGENTINA = timezone(timedelta(hours=-3))
CAMPOS_FECHA_HORA = ("DATE_CREATE", "DATE_MODIFY", "DATE_CLOSED")


def a_hora_argentina(valor):
    if not valor or not isinstance(valor, str) or "T" not in valor:
        return valor
    try:
        return datetime.fromisoformat(valor).astimezone(ARGENTINA).isoformat()
    except ValueError:
        return valor


def normalizar(snap: dict) -> dict:
    """Pasa a hora argentina los campos de fecha y hora del snapshot."""
    if snap.get("_hora_argentina"):
        return snap
    for fila in snap.get("prospectos", []) + snap.get("negociaciones", []):
        for campo in CAMPOS_FECHA_HORA:
            if fila.get(campo):
                fila[campo] = a_hora_argentina(fila[campo])
    snap["_hora_argentina"] = True
    return snap


def cargar(ruta) -> dict:
    return normalizar(json.loads(ruta.read_text(encoding="utf-8")))


def cargar_ultimo() -> dict:
    archivos = sorted(DIR_SNAPSHOTS.glob("*.json"))
    if not archivos:
        raise FileNotFoundError("No hay snapshots todavía. Corré: python3 run.py ingest")
    return cargar(archivos[-1])
