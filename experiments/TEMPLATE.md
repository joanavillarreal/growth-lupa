---
id: EXP-000
nombre: Nombre corto y concreto
canal: meta            # meta | google | redes_sociales | general | <clave de config/definitions.yaml>
estado: propuesto      # propuesto | corriendo | concluido | descartado
descripcion: >
  Qué es el experimento, en una o dos oraciones.
problema: >
  Qué está fallando hoy en el canal y cuánto cuesta. Con un número.
hipotesis: >
  Si hacemos X, esperamos que Y mejore, porque Z.
datos:                 # los números que respaldan la hipótesis, uno por línea
  - "Ejemplo: en el Q3 Meta derivó 26% contra 40% de Google"
solucion: >
  Qué se cambia exactamente, contra qué se compara y qué NO se toca durante la prueba.
metrica_primaria: cpl  # la única que decide: generados | cpl | pct_derivacion | costo_por_derivado | pct_no_calificacion | presupuestados
efecto_esperado: "-20%"
n_minimo: 150          # prospectos del canal necesarios para poder leer el resultado
lanzamiento: 2026-10-06
fin_analisis: 2026-11-02
responsable: ""
resultado: ""          # conclusión escrita al cerrar, aunque salga mal
decision: ""           # adoptar | descartar | repetir con cambios
---

Notas libres (opcional): qué pasó durante la prueba, cambios imprevistos, etc.
