/* ===================================================================== *
 *  runner.mjs — el lado JavaScript del arnes de paridad.
 *
 *  Lee del stdin un JSON `{"casos": [{id, op, args}, ...]}`, ejecuta cada
 *  caso contra `static/dominio.js` y escribe en stdout un JSON
 *  `{"resultados": {id: valor}}`. Un solo proceso para TODOS los casos:
 *  arrancar node por caso costaria minutos.
 *
 *  Regla del arnes: aqui no se calcula NADA. Cada `op` es una traduccion
 *  literal de la llamada que la prueba de Python hace del otro lado; si
 *  este archivo "arregla" un resultado, la comparacion deja de probar algo.
 * ===================================================================== */

// El modulo bajo prueba. Se puede apuntar a otra copia con DOMINIO_JS, que es
// lo que usa la prueba de mutacion del arnes: si mutar el JavaScript no produce
// divergencias, el arnes no esta comparando nada.
const _MODULO = process.env.DOMINIO_JS || "../../static/dominio.js";
const dominio = await import(_MODULO);

const {
  DominioError,
  // dinero
  tarifa, aplicar_tarifa, redondear_a_pesos, redondear_efectivo, a_pesos, de_pesos,
  formatear_cop, porcentaje, reparto_proporcional, MULTIPLO_EFECTIVO, CENTAVOS_POR_PESO,
  // documento
  calcular_dv_nit, verificar_dv_nit, separar_dv, normalizar, formatear_nit, validar,
  es_valido, DV_NIT_PESOS, REGLAS, TipoDocumento,
  // envio
  CIUDADES, TRANSPORTADORAS, SIN_CONTRAENTREGA, REGIMEN_IVA_ESPECIAL, Paquete,
  resolver_ciudad, buscar_ciudades, diagnostico_contraentrega, tope_contraentrega,
  cotizar, mejor_cotizacion, FLETE_EXCLUIDO_DE_IVA, FACTOR_VOLUMETRICO_CM3_POR_KG,
  PESO_FACTURABLE_MINIMO_GRAMOS,
  // impuesto
  LineaVenta, liquidar, liquidar_linea, resumen_descontables, TRATAMIENTOS,
  TARIFA_IVA_GENERAL, TARIFA_IVA_REDUCIDA, TARIFA_INC_RESTAURANTES, IMPUESTOS_SALUDABLES,
  // retracto
  pascua, festivos, es_festivo, es_dia_habil, sumar_dias_habiles, dias_habiles_entre,
  aplica_retracto, ventana_retracto, desde_iso, a_iso, CATEGORIAS_SIN_RETRACTO,
  DIAS_HABILES_RETRACTO, DIAS_PARA_DEVOLVER_DINERO,
  // pago
  ContextoPago, evaluar, recomendar, gmf, BANCOS_PSE, PARAMETROS_VIGENTES,
  TARIFA_GMF, TARIFA_RETEFUENTE_TARJETAS, UVT_EXENTAS_GMF_MENSUALES,
  SMMLV_TOPE_DEPOSITO_BAJO_MONTO, MetodoPago,
  // catalogo
  CATALOGO, COMERCIO, obtener, buscar, por_categoria, precio_al_publico, productos,
  armar_carrito, Categoria,
  // herramientas
  herramientas, contexto, salud,
} = dominio;

/* --------------------------------------------------------------------- *
 *  Serializacion: el Python del otro lado emite exactamente estas formas.
 * --------------------------------------------------------------------- */

const iso = (f) => (f === null || f === undefined ? null : a_iso(f));

/** Una cotizacion del dominio, con los nombres del dataclass de Python. */
function ser_cotizacion(c) {
  return {
    transportadora: c.transportadora,
    codigo_transportadora: c.codigo_transportadora,
    ciudad: c.ciudad.codigo_dane,
    peso_facturable_gramos: c.peso_facturable_gramos,
    flete_centavos: c.flete_centavos,
    recargo_aereo_centavos: c.recargo_aereo_centavos,
    manejo_centavos: c.manejo_centavos,
    recaudo_centavos: c.recaudo_centavos,
    dias_habiles_minimo: c.dias_habiles_minimo,
    dias_habiles_maximo: c.dias_habiles_maximo,
    contraentrega: c.contraentrega,
    notas: [...c.notas],
    total_centavos: c.total_centavos,
  };
}

function ser_linea(l) {
  return {
    descripcion: l.descripcion,
    cantidad: l.cantidad,
    regimen_solicitado: l.regimen_solicitado,
    regimen_aplicado: l.regimen_aplicado,
    tributo: l.tributo === undefined ? null : l.tributo,
    tarifa: porcentaje(l.tarifa),
    bruto_centavos: l.bruto_centavos,
    descuento_centavos: l.descuento_centavos,
    base_gravable_centavos: l.base_gravable_centavos,
    impuesto_centavos: l.impuesto_centavos,
    total_centavos: l.total_centavos,
    fundamento: l.fundamento,
    motivo_ajuste: l.motivo_ajuste === undefined ? null : l.motivo_ajuste,
    da_derecho_a_descontables: l.da_derecho_a_descontables,
  };
}

function ser_liquidacion(q) {
  const r = resumen_descontables(q);
  return {
    lineas: q.lineas.map(ser_linea),
    subtotales: q.subtotales.map((s) => ({
      tributo: s.tributo,
      tarifa: s.tarifa_porcentual,
      base_centavos: s.base_centavos,
      valor_centavos: s.valor_centavos,
    })),
    bruto_centavos: q.bruto_centavos,
    descuentos_centavos: q.descuentos_centavos,
    base_gravable_centavos: q.base_gravable_centavos,
    iva_centavos: q.iva_centavos,
    inc_centavos: q.inc_centavos,
    total_centavos: q.total_centavos,
    notas: [...q.notas],
    descontables: {
      base_con_derecho_centavos: r.base_con_derecho_centavos,
      base_sin_derecho_centavos: r.base_sin_derecho_centavos,
      nota: r.nota,
    },
  };
}

function ser_festivo(f) {
  return {
    fecha: iso(f.fecha),
    nombre: f.nombre,
    trasladado: f.trasladado,
    fecha_original: iso(f.fecha_original),
    fundamento: f.fundamento,
  };
}

function ser_evaluacion(e) {
  return {
    metodo: e.metodo,
    nombre: e.nombre,
    disponible: e.disponible,
    motivos: [...e.motivos],
    requisitos: [...e.requisitos],
    recargo_cliente_centavos: e.recargo_cliente_centavos,
    comision_centavos: e.comision_centavos,
    retencion_centavos: e.retencion_centavos,
    gmf_centavos: e.gmf_centavos,
    costo_total_comercio_centavos: e.costo_total_comercio_centavos,
    dias_habiles_liquidacion: e.dias_habiles_liquidacion,
    cuotas_maximas: e.cuotas_maximas,
    total_cliente_centavos: e.total_cliente_centavos,
    neto_comercio_centavos: e.neto_comercio_centavos,
    notas: [...e.notas],
  };
}

function ser_ciudad(c) {
  return {
    codigo_dane: c.codigo_dane,
    nombre: c.nombre,
    departamento: c.departamento,
    etiqueta: c.etiqueta,
    zona: c.zona,
    solo_aereo: c.solo_aereo,
    regimen_iva_especial: c.regimen_iva_especial,
  };
}

function ser_producto(p) {
  return {
    sku: p.sku,
    nombre: p.nombre,
    categoria: p.categoria,
    regimen: p.regimen,
    precio_base_centavos: p.precio_base_centavos,
    peso_gramos: p.peso_gramos,
    largo_cm: p.largo_cm,
    ancho_cm: p.ancho_cm,
    alto_cm: p.alto_cm,
    fundamento: p.fundamento,
    exclusiones_retracto: [...p.exclusiones_retracto].sort(),
    es_servicio: p.es_servicio,
    impuesto_saludable_incorporado: p.impuesto_saludable_incorporado,
  };
}

/** Construye las lineas de venta de una especificacion declarativa. */
const lineas_de = (spec) => spec.map((l) => LineaVenta(
  l.descripcion, l.regimen, l.precio, l.cantidad ?? 1, l.descuento ?? 0));

const ciudad_de = (x) => (x === null || x === undefined ? null : resolver_ciudad(x));

/* --------------------------------------------------------------------- *
 *  Tabla de operaciones. Una por llamada que el Python hace del otro lado.
 * --------------------------------------------------------------------- */

const OPS = {
  /* ---- dinero ---- */
  aplicar_tarifa: (a) => aplicar_tarifa(a.base, tarifa(a.num, a.den)),
  redondear_a_pesos: (a) => redondear_a_pesos(a.monto),
  redondear_efectivo: (a) => (a.multiplo === undefined
    ? redondear_efectivo(a.monto)
    : redondear_efectivo(a.monto, a.multiplo)),
  formatear_cop: (a) => formatear_cop(a.monto, { con_centavos: !!a.con_centavos }),
  a_pesos: (a) => a_pesos(a.monto),
  de_pesos: (a) => de_pesos(a.pesos),
  reparto_proporcional: (a) => reparto_proporcional(a.total, a.pesos),
  porcentaje: (a) => porcentaje(tarifa(a.num, a.den)),

  /* ---- documento ---- */
  calcular_dv_nit: (a) => calcular_dv_nit(a.base),
  verificar_dv_nit: (a) => verificar_dv_nit(a.base, a.dv),
  separar_dv: (a) => separar_dv(a.valor),
  normalizar: (a) => normalizar(a.valor),
  formatear_nit: (a) => formatear_nit(a.base, a.dv),
  es_valido: (a) => es_valido(a.tipo, a.valor),
  validar_documento: (a) => {
    const d = validar(a.tipo, a.valor);
    return {
      tipo: d.tipo,
      numero: d.numero,
      dv: d.dv,
      codigo_dian: d.codigo_dian,
      nombre_regla: d.regla.nombre,
      es_persona_juridica: d.es_persona_juridica,
      formateado: d.formateado,
      texto: d.toString(),
    };
  },
  documento_crudo: (a) => {
    const d = new dominio.Documento(a.tipo, a.numero, a.dv === undefined ? null : a.dv);
    return { tipo: d.tipo, numero: d.numero, dv: d.dv, texto: d.toString() };
  },

  /* ---- envio ---- */
  resolver_ciudad: (a) => ser_ciudad(resolver_ciudad(a.consulta)),
  buscar_ciudades: (a) => buscar_ciudades(a.texto).map((c) => c.codigo_dane),
  diagnostico_contraentrega: (a) => diagnostico_contraentrega(a.destino),
  tope_contraentrega: (a) => tope_contraentrega(a.destino),
  paquete: (a) => {
    const p = Paquete({
      peso_gramos: a.peso,
      largo_cm: a.largo ?? 20,
      ancho_cm: a.ancho ?? 20,
      alto_cm: a.alto ?? 15,
      valor_declarado_centavos: a.valor ?? 0,
    });
    return {
      peso_volumetrico_gramos: p.peso_volumetrico_gramos,
      peso_facturable_gramos: p.peso_facturable_gramos,
    };
  },
  cotizar: (a) => cotizar(
    a.destino,
    Paquete({
      peso_gramos: a.peso,
      largo_cm: a.largo ?? 20,
      ancho_cm: a.ancho ?? 20,
      alto_cm: a.alto ?? 15,
      valor_declarado_centavos: a.valor ?? 0,
    }),
    { contraentrega: !!a.contraentrega, monto_a_recaudar_centavos: a.monto ?? 0 },
  ).map(ser_cotizacion),
  mejor_cotizacion: (a) => {
    const m = mejor_cotizacion(
      a.destino,
      Paquete({
        peso_gramos: a.peso,
        largo_cm: a.largo ?? 20,
        ancho_cm: a.ancho ?? 20,
        alto_cm: a.alto ?? 15,
        valor_declarado_centavos: a.valor ?? 0,
      }),
      { contraentrega: !!a.contraentrega, monto_a_recaudar_centavos: a.monto ?? 0 },
    );
    return m === null ? null : ser_cotizacion(m);
  },

  /* ---- impuesto ---- */
  liquidar: (a) => ser_liquidacion(liquidar(lineas_de(a.lineas), {
    destino: ciudad_de(a.destino),
    responsable_iva: a.responsable_iva === undefined ? true : a.responsable_iva,
  })),
  liquidar_linea: (a) => ser_linea(liquidar_linea(lineas_de([a.linea])[0], {
    destino: ciudad_de(a.destino),
    responsable_iva: a.responsable_iva === undefined ? true : a.responsable_iva,
  })),
  linea_venta: (a) => {
    const l = LineaVenta(a.descripcion, a.regimen, a.precio, a.cantidad ?? 1, a.descuento ?? 0);
    return { bruto_centavos: l.bruto_centavos };
  },

  /* ---- retracto ---- */
  pascua: (a) => iso(pascua(a.anio)),
  festivos: (a) => festivos(a.anio).map(ser_festivo),
  es_festivo: (a) => es_festivo(desde_iso(a.fecha)),
  es_dia_habil: (a) => es_dia_habil(desde_iso(a.fecha), { sabado_habil: !!a.sabado_habil }),
  sumar_dias_habiles: (a) => iso(
    sumar_dias_habiles(desde_iso(a.inicio), a.dias, { sabado_habil: !!a.sabado_habil })),
  dias_habiles_entre: (a) => dias_habiles_entre(
    desde_iso(a.inicio), desde_iso(a.fin), { sabado_habil: !!a.sabado_habil }),
  aplica_retracto: (a) => aplica_retracto(a.modalidad, {
    exclusiones: a.exclusiones ? new Set(a.exclusiones) : null,
  }),
  ventana_retracto: (a) => {
    const v = ventana_retracto(desde_iso(a.fecha_entrega), {
      modalidad: a.modalidad ?? "domicilio",
      exclusiones: a.exclusiones ? new Set(a.exclusiones) : null,
      sabado_habil: !!a.sabado_habil,
    });
    const hoy = a.hoy ? desde_iso(a.hoy) : null;
    return {
      aplica: v.aplica,
      motivo: v.motivo,
      fecha_entrega: iso(v.fecha_entrega),
      inicio: iso(v.inicio),
      vence: iso(v.vence),
      dias_habiles: v.dias_habiles,
      festivos_intermedios: v.festivos_intermedios.map(ser_festivo),
      dias_para_devolver_dinero: v.dias_para_devolver_dinero,
      vigente: hoy ? v.vigente(hoy) : null,
      dias_habiles_restantes: hoy
        ? v.dias_habiles_restantes(hoy, { sabado_habil: !!a.sabado_habil })
        : null,
    };
  },

  /* ---- pago ---- */
  gmf: (a) => gmf(a.monto),
  evaluar: (a) => evaluar(ContextoPago({
    total_centavos: a.total,
    ciudad: resolver_ciudad(a.ciudad),
    base_sin_impuestos_centavos: a.base_sin_impuestos ?? 0,
    comision_recaudo_centavos: a.comision_recaudo ?? 0,
    contiene_servicios: !!a.contiene_servicios,
    banco_pse: a.banco_pse ?? null,
    cliente_tiene_bancolombia: !!a.cliente_tiene_bancolombia,
  })).map(ser_evaluacion),
  recomendar: (a) => recomendar(ContextoPago({
    total_centavos: a.total,
    ciudad: resolver_ciudad(a.ciudad),
    base_sin_impuestos_centavos: a.base_sin_impuestos ?? 0,
    comision_recaudo_centavos: a.comision_recaudo ?? 0,
    contiene_servicios: !!a.contiene_servicios,
    banco_pse: a.banco_pse ?? null,
    cliente_tiene_bancolombia: !!a.cliente_tiene_bancolombia,
  })).metodo,

  /* ---- catalogo ---- */
  obtener: (a) => ser_producto(obtener(a.sku)),
  buscar_catalogo: (a) => buscar(a.texto).map((p) => p.sku),
  por_categoria: (a) => por_categoria(a.categoria).map((p) => p.sku),
  precio_al_publico: (a) => precio_al_publico(obtener(a.sku), {
    destino: ciudad_de(a.destino),
    responsable_iva: a.responsable_iva === undefined ? true : a.responsable_iva,
    redondear: a.redondear === undefined ? true : a.redondear,
  }),
  carrito: (a) => {
    const c = armar_carrito(a.items.map((it) => [it.sku, it.cantidad ?? 1]));
    const base = {
      peso_gramos: c.peso_gramos,
      contiene_servicios: c.contiene_servicios,
      exclusiones_retracto: [...c.exclusiones_retracto].sort(),
      lleva_impuestos_saludables: c.lleva_impuestos_saludables,
      tiene_despachables: c.tiene_despachables,
      despachables: c.despachables.map((l) => [l.producto.sku, l.cantidad]),
      cantidades: c.lineas_venta().map((l) => l.cantidad),
      brutos: c.lineas_venta().map((l) => l.bruto_centavos),
    };
    if (!c.tiene_despachables) return { ...base, paquete: null };
    const p = c.paquete({ valor_declarado_centavos: a.valor_declarado ?? 0 });
    return {
      ...base,
      paquete: {
        peso_gramos: p.peso_gramos,
        largo_cm: p.largo_cm,
        ancho_cm: p.ancho_cm,
        alto_cm: p.alto_cm,
        valor_declarado_centavos: p.valor_declarado_centavos,
        peso_volumetrico_gramos: p.peso_volumetrico_gramos,
        peso_facturable_gramos: p.peso_facturable_gramos,
      },
    };
  },
  carrito_paquete: (a) => {
    const c = armar_carrito(a.items.map((it) => [it.sku, it.cantidad ?? 1]));
    const p = c.paquete({ valor_declarado_centavos: a.valor_declarado ?? 0 });
    return { peso_gramos: p.peso_gramos, alto_cm: p.alto_cm };
  },

  /* ---- las seis herramientas + contexto + salud ---- */
  herramienta: (a) => herramientas[a.nombre](a.payload),
  version: () => dominio.VERSION,
  contexto: () => contexto(),
  salud: () => {
    const s = salud();
    // La version la fija el paquete Python; comparar el numero de version
    // probaria el empaquetado, no el dominio.
    delete s.version;
    return s;
  },

  /* ---- tablas maestras completas ---- */
  tablas: () => ({
    dv_nit_pesos: [...DV_NIT_PESOS],
    tipos_documento: Object.values(TipoDocumento).slice().sort(),
    reglas: [...REGLAS.values()].map((r) => ({
      tipo: r.tipo,
      codigo_dian: r.codigo_dian,
      nombre: r.nombre,
      largo_minimo: r.largo_minimo,
      largo_maximo: r.largo_maximo,
      solo_digitos: r.solo_digitos,
      requiere_dv: r.requiere_dv,
    })),
    ciudades: [...CIUDADES.values()].map(ser_ciudad),
    sin_contraentrega: [...SIN_CONTRAENTREGA].sort(),
    regimen_iva_especial: [...REGIMEN_IVA_ESPECIAL].sort(),
    transportadoras: TRANSPORTADORAS.map((t) => ({
      codigo: t.codigo,
      nombre: t.nombre,
      nit: t.nit ?? null,
      ofrece_contraentrega: t.ofrece_contraentrega,
      comision_recaudo: porcentaje(t.comision_recaudo),
      recaudo_minimo_centavos: t.recaudo_minimo_centavos,
      recaudo_maximo_centavos: t.recaudo_maximo_centavos,
      comision_manejo: porcentaje(t.comision_manejo),
      manejo_minimo_centavos: t.manejo_minimo_centavos,
      sin_cobertura: [...t.sin_cobertura].sort(),
      tarifas: [...t.tarifas.entries()]
        .sort((x, y) => (x[0] < y[0] ? -1 : x[0] > y[0] ? 1 : 0))
        .map(([zona, z]) => ({
        zona,
        base_centavos: z.base_centavos,
        kilos_incluidos: z.kilos_incluidos,
        adicional_por_kilo_centavos: z.adicional_por_kilo_centavos,
        dias_habiles_minimo: z.dias_habiles_minimo,
        dias_habiles_maximo: z.dias_habiles_maximo,
      })),
    })),
    factor_volumetrico: FACTOR_VOLUMETRICO_CM3_POR_KG,
    peso_facturable_minimo: PESO_FACTURABLE_MINIMO_GRAMOS,
    flete_excluido_de_iva: FLETE_EXCLUIDO_DE_IVA,
    tratamientos: [...TRATAMIENTOS.entries()].map(([regimen, t]) => ({
      regimen,
      tributo: t.tributo,
      tarifa: porcentaje(t.tarifa),
      causa_impuesto: t.causa_impuesto,
      da_derecho_a_descontables: t.da_derecho_a_descontables,
      fundamento: t.fundamento,
      explicacion: t.explicacion,
    })),
    tarifas_iva: [
      porcentaje(TARIFA_IVA_GENERAL),
      porcentaje(TARIFA_IVA_REDUCIDA),
      porcentaje(TARIFA_INC_RESTAURANTES),
    ],
    impuestos_saludables: IMPUESTOS_SALUDABLES,
    categorias_sin_retracto: [...CATEGORIAS_SIN_RETRACTO].sort(),
    dias_habiles_retracto: DIAS_HABILES_RETRACTO,
    dias_para_devolver_dinero: DIAS_PARA_DEVOLVER_DINERO,
    bancos_pse: [...BANCOS_PSE].sort(),
    metodos_pago: Object.values(MetodoPago),
    parametros: {
      anio: PARAMETROS_VIGENTES.anio,
      uvt_centavos: PARAMETROS_VIGENTES.uvt_centavos,
      smmlv_centavos: PARAMETROS_VIGENTES.smmlv_centavos,
      tope_deposito_bajo_monto_centavos: PARAMETROS_VIGENTES.tope_deposito_bajo_monto_centavos,
      exencion_gmf_mensual_centavos: PARAMETROS_VIGENTES.exencion_gmf_mensual_centavos,
    },
    tarifa_gmf: porcentaje(TARIFA_GMF),
    tarifa_retefuente: porcentaje(TARIFA_RETEFUENTE_TARJETAS),
    uvt_exentas: UVT_EXENTAS_GMF_MENSUALES,
    smmlv_tope: SMMLV_TOPE_DEPOSITO_BAJO_MONTO,
    catalogo: productos().map(ser_producto),
    categorias: Object.values(Categoria),
    comercio: {
      nombre: COMERCIO.nombre,
      documento: COMERCIO.documento.toString(),
      codigo_dian: COMERCIO.documento.codigo_dian,
      direccion: COMERCIO.direccion,
      ciudad_codigo_dane: COMERCIO.ciudad_codigo_dane,
      responsable_iva: COMERCIO.responsable_iva,
      correo: COMERCIO.correo,
    },
    multiplo_efectivo: MULTIPLO_EFECTIVO,
    centavos_por_peso: CENTAVOS_POR_PESO,
  }),
};

/* --------------------------------------------------------------------- *
 *  Bucle principal
 * --------------------------------------------------------------------- */

function leer_stdin() {
  const trozos = [];
  return new Promise((resolve, reject) => {
    process.stdin.on("data", (t) => trozos.push(t));
    process.stdin.on("end", () => resolve(Buffer.concat(trozos).toString("utf8")));
    process.stdin.on("error", reject);
  });
}

const entrada = JSON.parse(await leer_stdin());
const resultados = {};

for (const caso of entrada.casos) {
  const op = OPS[caso.op];
  if (!op) {
    resultados[caso.id] = { __arnes__: `operacion desconocida: ${caso.op}` };
    continue;
  }
  try {
    resultados[caso.id] = { valor: op(caso.args || {}) };
  } catch (err) {
    resultados[caso.id] = {
      error: {
        clase: err instanceof DominioError ? err.constructor.name : "Error",
        mensaje: err && err.message !== undefined ? String(err.message) : String(err),
      },
    };
  }
}

process.stdout.write(JSON.stringify({ resultados }));
