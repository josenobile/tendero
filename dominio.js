/* ===================================================================== *
 *  dominio.js — las reglas colombianas de Tendero, dentro de la página.
 *
 *  Este archivo es el port literal de `src/tendero/domain/` a JavaScript.
 *  El Python es la ESPECIFICACIÓN: está cubierto por 363 pruebas al 100 %
 *  y donde los dos difieran, el que está mal es este archivo. Cada sección
 *  lleva el nombre del módulo del que viene para que la comparación sea
 *  línea a línea.
 *
 *  Por qué existe:
 *    · la página deja de necesitar backend y se puede publicar estática;
 *    · durante una evaluación no hay servidor que se pueda caer;
 *    · y es más fiel a WebMCP — la premisa de la especificación es que la
 *      PÁGINA expone sus propias capacidades. Una página que reenvía cada
 *      llamada a un servidor usa WebMCP como un cascarón.
 *
 *  Tres invariantes que no se pueden romper al portar:
 *
 *   1. EL DINERO SON CENTAVOS ENTEROS. Nunca un float. Los enteros hasta
 *      2^53 son exactos en IEEE-754, así que los centavos caben de sobra,
 *      pero TODA división redondea explícitamente con `_mitad_arriba`, que
 *      reproduce el ROUND_HALF_UP de `decimal.Decimal` (el medio se aleja
 *      del cero, no "al par"). La DIAN valida que la suma de los impuestos
 *      línea a línea coincida al centavo con el total del documento: medio
 *      centavo de deriva rechaza la factura completa.
 *
 *   2. LAS TARIFAS SON FRACCIONES EXACTAS `{num, den}`, no decimales. En
 *      JavaScript `0.19 * 100 === 19.000000000000004`. Una tarifa escrita
 *      como número flotante mete error donde el Python usa Decimal("0.19"),
 *      que es exacto. Con 19/100 la aritmética vuelve a ser entera.
 *
 *   3. LAS FECHAS SON UTC, SIEMPRE. Un `new Date(2026, 3, 2)` en Bogotá
 *      (UTC-5) nace a las 05:00Z y cualquier `toISOString()` posterior se
 *      corre de día. Ese es el error clásico de este port y se evita a
 *      propósito: aquí sólo hay `Date.UTC`, `getUTC*` y sumas de 86400000.
 *
 *  Sin dependencias, sin build, sin red. Módulo ES, se importa así:
 *      import * as dominio from "./dominio.js";
 * ===================================================================== */

"use strict";

/* ===================================================================== *
 *  errores.py — errores del dominio
 *
 *  Se separan para que la capa WebMCP pueda mapear cada uno a un mensaje
 *  accionable: un fallo de validación de documento no es lo mismo que una
 *  ciudad sin cobertura, y el agente debe poder reintentar sólo el primero.
 * ===================================================================== */

export class DominioError extends Error {
  constructor(mensaje) {
    super(mensaje);
    this.name = "DominioError";
  }
}

export class DocumentoInvalidoError extends DominioError {
  constructor(mensaje) {
    super(mensaje);
    this.name = "DocumentoInvalidoError";
  }
}

export class CiudadDesconocidaError extends DominioError {
  constructor(mensaje) {
    super(mensaje);
    this.name = "CiudadDesconocidaError";
  }
}

export class ProductoDesconocidoError extends DominioError {
  constructor(mensaje) {
    super(mensaje);
    this.name = "ProductoDesconocidoError";
  }
}

export class MetodoPagoError extends DominioError {
  constructor(mensaje) {
    super(mensaje);
    this.name = "MetodoPagoError";
  }
}

/* ===================================================================== *
 *  dinero.py — aritmética monetaria en centavos de peso colombiano
 * ===================================================================== */

export const CENTAVOS_POR_PESO = 100;

/** La moneda más pequeña en circulación es la de cincuenta pesos.
 *  El pago en efectivo (y por tanto el contraentrega) se redondea a ese
 *  múltiplo porque el mensajero no puede dar cambio por debajo de él. */
export const MULTIPLO_EFECTIVO = 50 * CENTAVOS_POR_PESO;

/**
 * Una tarifa fraccionaria EXACTA. `tarifa(19, 100)` es lo que en Python es
 * `Decimal("0.19")`. No se guarda como número decimal a propósito: ver la
 * invariante 2 de la cabecera.
 */
export function tarifa(num, den) {
  return Object.freeze({ num, den });
}

export const TARIFA_CERO = tarifa(0, 1);

/**
 * División con redondeo ROUND_HALF_UP de `decimal.Decimal`: el medio se
 * aleja del cero (0,5 → 1 y −0,5 → −1), NO al par como `Math.round` de un
 * negativo ni como el banker's rounding de otros lenguajes.
 *
 * Identidad usada: para n, d > 0, redondear n/d con el medio hacia arriba
 * es exactamente floor((2n + d) / (2d)).
 */
function _mitad_arriba(n, d) {
  if (d <= 0) throw new Error("el divisor debe ser positivo");
  const signo = n < 0 ? -1 : 1;
  const a = Math.abs(n);
  return signo * Math.floor((2 * a + d) / (2 * d));
}

/** Aplica una tarifa fraccionaria a una base y redondea a centavo entero. */
export function aplicar_tarifa(base, tar) {
  return _mitad_arriba(base * tar.num, tar.den);
}

/** Lleva el monto al peso entero más cercano (los centavos no circulan). */
export function redondear_a_pesos(monto) {
  return _mitad_arriba(monto, CENTAVOS_POR_PESO) * CENTAVOS_POR_PESO;
}

/**
 * Redondea al múltiplo pagable en efectivo más cercano.
 * Se usa para el contraentrega: el valor a recaudar tiene que ser una cifra
 * que el cliente pueda entregar y el mensajero devolver con monedas reales.
 */
export function redondear_efectivo(monto, multiplo = MULTIPLO_EFECTIVO) {
  if (multiplo <= 0) throw new Error("el multiplo de redondeo debe ser positivo");
  return _mitad_arriba(monto, multiplo) * multiplo;
}

/** Convierte centavos a pesos con dos decimales exactos, como texto. */
export function a_pesos(monto) {
  const negativo = monto < 0;
  const absoluto = Math.abs(monto);
  const pesos = Math.floor(absoluto / CENTAVOS_POR_PESO);
  const centavos = absoluto - pesos * CENTAVOS_POR_PESO;
  return `${negativo ? "-" : ""}${pesos}.${String(centavos).padStart(2, "0")}`;
}

/**
 * Convierte una cifra en pesos a centavos enteros sin pasar por float.
 * El texto se descompone con expresión regular en vez de `parseFloat`
 * justamente para no heredar el error de representación binaria.
 */
export function de_pesos(pesos) {
  const texto = String(pesos).trim();
  const m = /^([+-]?)(\d*)(?:\.(\d*))?$/.exec(texto);
  if (!m || (m[2] === "" && (m[3] === undefined || m[3] === ""))) {
    throw new Error(`no es una cifra en pesos: ${_repr(pesos)}`);
  }
  const signo = m[1] === "-" ? -1 : 1;
  const enteros = m[2] === "" ? 0 : Number(m[2]);
  const decimales = m[3] || "";
  // Se redondea la fracción a centavo con el mismo criterio del Python.
  const escala = 10 ** decimales.length;
  const fraccion = decimales === "" ? 0 : Number(decimales);
  const centavos = enteros * CENTAVOS_POR_PESO +
    (escala === 1 ? 0 : _mitad_arriba(fraccion * CENTAVOS_POR_PESO, escala));
  return signo * centavos;
}

/** Agrupa de a tres con punto, la convención colombiana de miles. */
function _agrupar(entero) {
  return String(entero).replace(/\B(?=(\d{3})+(?!\d))/g, ".");
}

/** Agrupa una cadena de dígitos como lo haría `f"{int(s):,}"` en Python. */
function _agrupar_digitos(digitos) {
  return _agrupar(digitos.replace(/^0+(?=\d)/, ""));
}

/** Formatea en la convención colombiana: punto de miles, coma decimal. */
export function formatear_cop(monto, { con_centavos = false } = {}) {
  const negativo = monto < 0;
  const absoluto = Math.abs(monto);
  const pesos = Math.floor(absoluto / CENTAVOS_POR_PESO);
  const centavos = absoluto - pesos * CENTAVOS_POR_PESO;
  const entero = _agrupar(pesos);
  const cuerpo = con_centavos ? `${entero},${String(centavos).padStart(2, "0")}` : entero;
  return `${negativo ? "-" : ""}$ ${cuerpo}`;
}

/**
 * Tarifa como la imprime una factura colombiana: dos decimales, coma.
 * Se calcula en centésimas de punto porcentual con aritmética entera para
 * no reintroducir el 19.000000000000004 que la invariante 2 evita.
 */
export function porcentaje(tar) {
  const centesimas = _mitad_arriba(tar.num * 10000, tar.den);
  const signo = centesimas < 0 ? "-" : "";
  const a = Math.abs(centesimas);
  return `${signo}${Math.floor(a / 100)},${String(a % 100).padStart(2, "0")}`;
}

/**
 * Reparte `total` entre n destinos sin perder ni inventar centavos.
 * El residuo del prorrateo cae siempre en la última parte: si el reparto no
 * cierra al centavo, la base gravable declarada deja de cuadrar con el total.
 */
export function reparto_proporcional(total, pesos_relativos) {
  if (!pesos_relativos.length) return [];
  const suma = pesos_relativos.reduce((a, b) => a + b, 0);
  if (suma <= 0) throw new Error("los pesos relativos deben sumar un valor positivo");
  let asignado = 0;
  const partes = [];
  for (const peso of pesos_relativos.slice(0, -1)) {
    const parte = _mitad_arriba(total * peso, suma);
    partes.push(parte);
    asignado += parte;
  }
  partes.push(total - asignado);
  return partes;
}

/* ===================================================================== *
 *  documento.py — identidades tributarias DIAN
 *
 *  Un dígito de verificación mal calculado hace que la DIAN rechace el
 *  documento electrónico completo. Es la regla que más veces rompe una
 *  integración nueva, y por eso vive en el dominio y no en la vista.
 * ===================================================================== */

/** Serie completa de primos que la DIAN aplica de DERECHA A IZQUIERDA. */
const _SERIE_OFICIAL_DV = Object.freeze([71, 67, 59, 53, 47, 43, 41, 37, 29, 23, 19, 17, 13, 7, 3]);

/** (41, 37, 29, 23, 19, 17, 13, 7, 3): la cola usada por un NIT de 9 dígitos. */
export const DV_NIT_PESOS = Object.freeze(_SERIE_OFICIAL_DV.slice(-9));

const _MODULO_DV = 11;
const _RESIDUOS_CERO = new Set([0, 1]);

const _SEPARADORES = /[\s.,\-]/g;
const _SOLO_DIGITOS = /^[0-9]+$/;
const _ALFANUMERICO = /^[A-Z0-9]+$/;
const _NIT_CON_DV = /^\s*([\d.\s,]+?)\s*-\s*(\d)\s*$/;

/** La DIAN asigna NIT que empiezan en 8 o 9 a personas jurídicas.
 *  Una persona natural usa como NIT su propia cédula, que empieza en otro
 *  dígito. La distinción decide si la factura lleva razón social o nombres. */
const _PREFIJOS_PERSONA_JURIDICA = new Set(["8", "9"]);

export const TipoDocumento = Object.freeze({
  CC: "CC",
  CE: "CE",
  NIT: "NIT",
  PA: "PA",
  TI: "TI",
  PEP: "PEP",
});

export const REGLAS = new Map([
  ["CC", Object.freeze({
    tipo: "CC", codigo_dian: "13", nombre: "Cedula de ciudadania",
    largo_minimo: 4, largo_maximo: 10, solo_digitos: true, requiere_dv: false,
  })],
  ["CE", Object.freeze({
    tipo: "CE", codigo_dian: "22", nombre: "Cedula de extranjeria",
    largo_minimo: 5, largo_maximo: 8, solo_digitos: true, requiere_dv: false,
  })],
  ["NIT", Object.freeze({
    tipo: "NIT", codigo_dian: "31", nombre: "NIT",
    largo_minimo: 5, largo_maximo: 15, solo_digitos: true, requiere_dv: true,
  })],
  ["PA", Object.freeze({
    tipo: "PA", codigo_dian: "41", nombre: "Pasaporte",
    largo_minimo: 5, largo_maximo: 16, solo_digitos: false, requiere_dv: false,
  })],
  ["TI", Object.freeze({
    tipo: "TI", codigo_dian: "12", nombre: "Tarjeta de identidad",
    largo_minimo: 10, largo_maximo: 11, solo_digitos: true, requiere_dv: false,
  })],
  ["PEP", Object.freeze({
    tipo: "PEP", codigo_dian: "47", nombre: "Permiso Especial de Permanencia",
    largo_minimo: 15, largo_maximo: 15, solo_digitos: true, requiere_dv: false,
  })],
]);

/**
 * Reproduce `repr()` de Python sobre una cadena: comilla simple salvo que el
 * texto ya lleve una y no lleve dobles. Los mensajes de error del dominio son
 * parte del contrato — el agente los lee y la vitrina los pinta — así que
 * tienen que salir carácter por carácter iguales a los del backend.
 */
function _repr(valor) {
  const s = String(valor);
  const comilla = s.includes("'") && !s.includes('"') ? '"' : "'";
  let cuerpo = s.replace(/\\/g, "\\\\")
    .replace(/\n/g, "\\n").replace(/\r/g, "\\r").replace(/\t/g, "\\t");
  if (comilla === "'") cuerpo = cuerpo.replace(/'/g, "\\'");
  return comilla + cuerpo + comilla;
}

/** Quita puntos, comas, guiones y espacios y pasa a mayúsculas. */
export function normalizar(valor) {
  return String(valor).trim().toUpperCase().replace(_SEPARADORES, "");
}

/**
 * Parte `890.903.938-8` en base normalizada y dígito de verificación.
 * Hay que separar ANTES de normalizar: si se quitan los guiones primero,
 * `8909039388` es indistinguible de un NIT de diez dígitos sin DV.
 */
export function separar_dv(valor) {
  const coincidencia = _NIT_CON_DV.exec(String(valor));
  if (coincidencia === null) return [normalizar(valor), null];
  return [normalizar(coincidencia[1]), Number(coincidencia[2])];
}

/**
 * Dígito de verificación DIAN de un NIT sin DV.
 *
 * Cada dígito se multiplica, DE DERECHA A IZQUIERDA, por la serie oficial de
 * primos; la suma se toma módulo once y el residuo cero o uno produce un DV
 * cero, cualquier otro produce once menos el residuo. La regla del residuo
 * es la parte que casi todas las integraciones fallan.
 */
export function calcular_dv_nit(base) {
  const limpio = normalizar(base);
  if (!_SOLO_DIGITOS.test(limpio)) {
    throw new DocumentoInvalidoError(
      `el NIT solo admite digitos, se recibio ${_repr(base)}`);
  }
  if (limpio.length > _SERIE_OFICIAL_DV.length) {
    throw new DocumentoInvalidoError(
      `NIT de ${limpio.length} digitos excede el maximo de la serie DIAN`);
  }
  let total = 0;
  for (let i = 0; i < limpio.length; i += 1) {
    // i = 0 es el dígito más a la derecha; le toca el último peso de la serie.
    const digito = Number(limpio[limpio.length - 1 - i]);
    const peso = _SERIE_OFICIAL_DV[_SERIE_OFICIAL_DV.length - 1 - i];
    total += digito * peso;
  }
  const residuo = total % _MODULO_DV;
  if (_RESIDUOS_CERO.has(residuo)) return 0;
  return _MODULO_DV - residuo;
}

/** Indica si `dv` es el dígito de verificación que corresponde a `base`. */
export function verificar_dv_nit(base, dv) {
  return calcular_dv_nit(base) === dv;
}

/** Devuelve el NIT en la presentación de la cámara de comercio. */
export function formatear_nit(base, dv) {
  return `${_agrupar_digitos(normalizar(base))}-${dv}`;
}

/** Identidad tributaria validada de un adquiriente. */
export class Documento {
  constructor(tipo, numero, dv = null) {
    const regla = REGLAS.get(tipo);
    if (!regla) {
      const admitidos = Object.values(TipoDocumento).slice().sort().join(", ");
      throw new DocumentoInvalidoError(
        `tipo de documento desconocido ${_repr(tipo)}; admitidos: ${admitidos}`);
    }
    if (numero !== normalizar(numero)) {
      throw new DocumentoInvalidoError(
        `el numero debe venir normalizado, se recibio ${_repr(numero)}`);
    }
    if (!numero) {
      throw new DocumentoInvalidoError(`${regla.nombre}: el numero no puede ir vacio`);
    }
    const patron = regla.solo_digitos ? _SOLO_DIGITOS : _ALFANUMERICO;
    if (!patron.test(numero)) {
      const forma = regla.solo_digitos ? "solo digitos" : "letras y digitos";
      throw new DocumentoInvalidoError(
        `${regla.nombre}: admite ${forma}, se recibio ${_repr(numero)}`);
    }
    if (numero.length < regla.largo_minimo || numero.length > regla.largo_maximo) {
      throw new DocumentoInvalidoError(
        `${regla.nombre}: longitud ${numero.length} fuera del rango ` +
        `${regla.largo_minimo}-${regla.largo_maximo}`);
    }
    if (regla.requiere_dv) {
      if (dv === null || dv === undefined) {
        throw new DocumentoInvalidoError(`${regla.nombre}: falta el digito de verificacion`);
      }
      const esperado = calcular_dv_nit(numero);
      if (esperado !== dv) {
        throw new DocumentoInvalidoError(
          `digito de verificacion incorrecto para el NIT ${numero}: ` +
          `se recibio ${dv}, corresponde ${esperado}`);
      }
    } else if (dv !== null && dv !== undefined) {
      throw new DocumentoInvalidoError(`${regla.nombre}: no lleva digito de verificacion`);
    }
    this.tipo = tipo;
    this.numero = numero;
    this.dv = regla.requiere_dv ? dv : null;
    Object.freeze(this);
  }

  /**
   * Construye un documento desde el texto tal como lo escribe una persona.
   * Acepta `890.903.938-8`, `890903938-8` y `890903938`: en el último caso
   * CALCULA el DV en vez de rechazar, porque el cliente de una tienda casi
   * nunca se lo sabe.
   */
  static parse(tipo, valor) {
    const clave = String(tipo).trim().toUpperCase();
    const regla = REGLAS.get(clave);
    if (!regla) {
      const admitidos = Object.values(TipoDocumento).slice().sort().join(", ");
      throw new DocumentoInvalidoError(
        `tipo de documento desconocido ${_repr(tipo)}; admitidos: ${admitidos}`);
    }
    if (regla.requiere_dv) {
      const [base, dictado] = separar_dv(valor);
      const dv = dictado === null ? calcular_dv_nit(base) : dictado;
      return new Documento(clave, base, dv);
    }
    return new Documento(clave, normalizar(valor));
  }

  get regla() { return REGLAS.get(this.tipo); }

  get codigo_dian() { return this.regla.codigo_dian; }

  /** Cierto si el NIT fue asignado a una empresa y no a una persona. */
  get es_persona_juridica() {
    return this.tipo === TipoDocumento.NIT && _PREFIJOS_PERSONA_JURIDICA.has(this.numero[0]);
  }

  /** Presentación legible para mostrarle el dato al cliente. */
  get formateado() {
    if (this.tipo === TipoDocumento.NIT && this.dv !== null) {
      return formatear_nit(this.numero, this.dv);
    }
    if (this.regla.solo_digitos) return _agrupar_digitos(this.numero);
    return this.numero;
  }

  toString() { return `${this.tipo} ${this.formateado}`; }
}

/** Valida y normaliza; lanza `DocumentoInvalidoError` si no cumple. */
export function validar(tipo, valor) {
  return Documento.parse(tipo, valor);
}

/** Versión booleana de `validar`, para ramas de decisión. */
export function es_valido(tipo, valor) {
  try {
    validar(tipo, valor);
    return true;
  } catch (err) {
    if (err instanceof DocumentoInvalidoError) return false;
    throw err;
  }
}

/* ===================================================================== *
 *  envio.py — cotización de flete nacional desde Medellín
 *
 *  El costo de llevar una caja en Colombia no depende de la distancia sino
 *  de si el destino está en un área metropolitana, en una ciudad intermedia
 *  o en un municipio al que sólo se llega por avión o por río. Leticia,
 *  Mitú, Inírida, Puerto Carreño, San Andrés y Providencia no tienen
 *  carretera: la mercancía viaja como carga aérea, la entrega final la hace
 *  un agente local y por eso NINGUNA transportadora recauda allí.
 *
 *  Esa asimetría es el punto del módulo, y del proyecto entero: el medio de
 *  pago que domina el comercio electrónico colombiano — pagar en efectivo
 *  cuando llega el paquete — depende de la ciudad, y la herramienta tiene
 *  que poder decir que no.
 * ===================================================================== */

/** Divisor que las transportadoras colombianas usan para el peso volumétrico. */
export const FACTOR_VOLUMETRICO_CM3_POR_KG = 6000;

/** Ninguna guía se cobra por debajo de un kilo, así vaya vacía. */
export const PESO_FACTURABLE_MINIMO_GRAMOS = 1000;

export const FLETE_EXCLUIDO_DE_IVA =
  "Art. 476 num. 2 ET: el transporte nacional de carga esta excluido del IVA. " +
  "Por eso el flete se suma al total del pedido sin impuesto y no entra a la " +
  "base gravable de la factura.";

const _RECARGO_AEREO_EXTRA = tarifa(65, 100);   // 1,65 − 1 en fracción exacta
const _RECARGO_AEREO_FIJO = 12000 * 100;
const _DIAS_EXTRA_AEREO = 3;
const _GRAMOS_POR_KILO = 1000;

export const Zona = Object.freeze({
  METROPOLITANA: "metropolitana",
  INTERMEDIA: "intermedia",
  REMOTA: "remota",
});

const _M = Zona.METROPOLITANA;
const _I = Zona.INTERMEDIA;
const _R = Zona.REMOTA;

function _c(codigo, nombre, departamento, zona, { aereo = false, iva_especial = false } = {}) {
  return [codigo, Object.freeze({
    codigo_dane: codigo,
    nombre,
    departamento,
    zona,
    solo_aereo: aereo,
    regimen_iva_especial: iva_especial,
    // Siempre con departamento: hay varios municipios llamados Caldas.
    etiqueta: `${nombre}, ${departamento}`,
  })];
}

/* Se usa Map y no un objeto literal a propósito: las claves DANE como
 * "11001" son cadenas de dígito canónico y un objeto de JavaScript las
 * reordenaría numéricamente delante de "05001". El orden de inserción es
 * parte del contrato (la vitrina pinta el selector en este orden). */
export const CIUDADES = new Map([
  _c("05001", "Medellin", "Antioquia", _M),
  _c("05088", "Bello", "Antioquia", _M),
  _c("05266", "Envigado", "Antioquia", _M),
  _c("05360", "Itagui", "Antioquia", _M),
  _c("05631", "Sabaneta", "Antioquia", _M),
  _c("05380", "La Estrella", "Antioquia", _M),
  _c("05129", "Caldas", "Antioquia", _M),
  _c("05212", "Copacabana", "Antioquia", _M),
  _c("05308", "Girardota", "Antioquia", _M),
  _c("05079", "Barbosa", "Antioquia", _M),
  _c("11001", "Bogota D.C.", "Bogota D.C.", _M),
  _c("25754", "Soacha", "Cundinamarca", _M),
  _c("25175", "Chia", "Cundinamarca", _M),
  _c("76001", "Cali", "Valle del Cauca", _M),
  _c("08001", "Barranquilla", "Atlantico", _M),
  _c("08758", "Soledad", "Atlantico", _M),
  _c("05615", "Rionegro", "Antioquia", _I),
  _c("05045", "Apartado", "Antioquia", _I),
  _c("05837", "Turbo", "Antioquia", _I),
  _c("13001", "Cartagena", "Bolivar", _I),
  _c("68001", "Bucaramanga", "Santander", _I),
  _c("66001", "Pereira", "Risaralda", _I),
  _c("17001", "Manizales", "Caldas", _I),
  _c("63001", "Armenia", "Quindio", _I),
  _c("47001", "Santa Marta", "Magdalena", _I),
  _c("54001", "Cucuta", "Norte de Santander", _I),
  _c("50001", "Villavicencio", "Meta", _I),
  _c("73001", "Ibague", "Tolima", _I),
  _c("52001", "Pasto", "Narino", _I),
  _c("41001", "Neiva", "Huila", _I),
  _c("23001", "Monteria", "Cordoba", _I),
  _c("19001", "Popayan", "Cauca", _I),
  _c("70001", "Sincelejo", "Sucre", _I),
  _c("20001", "Valledupar", "Cesar", _I),
  _c("15001", "Tunja", "Boyaca", _I),
  _c("85001", "Yopal", "Casanare", _I),
  _c("76109", "Buenaventura", "Valle del Cauca", _I),
  _c("44001", "Riohacha", "La Guajira", _I),
  _c("27001", "Quibdo", "Choco", _R),
  _c("18001", "Florencia", "Caqueta", _R),
  _c("81001", "Arauca", "Arauca", _R),
  _c("86001", "Mocoa", "Putumayo", _R),
  _c("95001", "San Jose del Guaviare", "Guaviare", _R),
  _c("88001", "San Andres", "Archipielago de San Andres", _R, { aereo: true, iva_especial: true }),
  _c("88564", "Providencia", "Archipielago de San Andres", _R, { aereo: true, iva_especial: true }),
  _c("91001", "Leticia", "Amazonas", _R, { aereo: true, iva_especial: true }),
  _c("91540", "Puerto Narino", "Amazonas", _R, { aereo: true, iva_especial: true }),
  _c("94001", "Inirida", "Guainia", _R, { aereo: true, iva_especial: true }),
  _c("97001", "Mitu", "Vaupes", _R, { aereo: true, iva_especial: true }),
  _c("99001", "Puerto Carreno", "Vichada", _R, { aereo: true }),
]);

/**
 * Destinos donde la venta no causa IVA.
 * San Andrés y Providencia por el Art. 423 del Estatuto Tributario;
 * Amazonas, Guainía y Vaupés por el Art. 270 de la Ley 223 de 1995.
 * El DESTINO, no el producto, cambia el impuesto.
 */
export const REGIMEN_IVA_ESPECIAL = new Set(
  [...CIUDADES.values()].filter((c) => c.regimen_iva_especial).map((c) => c.codigo_dane));

/** Destinos sin recaudo contra entrega: la entrega final la hace un tercero. */
export const SIN_CONTRAENTREGA = new Set(
  [...CIUDADES.values()].filter((c) => c.solo_aereo).map((c) => c.codigo_dane));

function _tarifas(metro, intermedia, remota, { kilos_incluidos = 1 } = {}) {
  const plazos = { [_M]: [1, 2], [_I]: [2, 4], [_R]: [4, 8] };
  const crudo = { [_M]: metro, [_I]: intermedia, [_R]: remota };
  const tabla = new Map();
  for (const zona of [_M, _I, _R]) {
    const valores = crudo[zona];
    if (!valores) continue;
    const [minimo, maximo] = plazos[zona];
    tabla.set(zona, Object.freeze({
      base_centavos: valores[0],
      kilos_incluidos,
      adicional_por_kilo_centavos: valores[1],
      dias_habiles_minimo: minimo,
      dias_habiles_maximo: maximo,
    }));
  }
  return tabla;
}

export const TRANSPORTADORAS = Object.freeze([
  Object.freeze({
    codigo: "servientrega",
    nombre: "Servientrega",
    nit: "860512330-3",
    tarifas: _tarifas([950000, 320000], [1590000, 450000], [2980000, 890000]),
    ofrece_contraentrega: true,
    comision_recaudo: tarifa(45, 1000),
    recaudo_minimo_centavos: 700000,
    recaudo_maximo_centavos: 200000000,
    comision_manejo: tarifa(10, 1000),
    manejo_minimo_centavos: 250000,
    sin_cobertura: new Set(),
  }),
  Object.freeze({
    codigo: "interrapidisimo",
    nombre: "Inter Rapidisimo",
    nit: "830029788-2",
    tarifas: _tarifas([820000, 290000], [1390000, 410000], [2750000, 820000]),
    ofrece_contraentrega: true,
    comision_recaudo: tarifa(40, 1000),
    recaudo_minimo_centavos: 600000,
    recaudo_maximo_centavos: 200000000,
    comision_manejo: tarifa(10, 1000),
    manejo_minimo_centavos: 200000,
    sin_cobertura: new Set(["88564", "94001", "97001", "99001", "91540"]),
  }),
  Object.freeze({
    codigo: "coordinadora",
    nombre: "Coordinadora",
    nit: null,
    tarifas: _tarifas([1100000, 350000], [1850000, 520000], [3400000, 980000]),
    ofrece_contraentrega: false,
    comision_recaudo: TARIFA_CERO,
    recaudo_minimo_centavos: 0,
    recaudo_maximo_centavos: 0,
    comision_manejo: tarifa(12, 1000),
    manejo_minimo_centavos: 300000,
    sin_cobertura: new Set(["88564", "91540", "94001", "97001", "99001"]),
  }),
  Object.freeze({
    codigo: "envia",
    nombre: "Envia",
    nit: null,
    tarifas: _tarifas([890000, 300000], [1480000, 430000], null),
    ofrece_contraentrega: true,
    comision_recaudo: tarifa(45, 1000),
    recaudo_minimo_centavos: 650000,
    recaudo_maximo_centavos: 150000000,
    comision_manejo: tarifa(10, 1000),
    manejo_minimo_centavos: 250000,
    sin_cobertura: new Set(),
  }),
  Object.freeze({
    codigo: "rapidito_aburra",
    nombre: "Rapidito Aburra (mensajeria local)",
    nit: "901234567-7",
    tarifas: _tarifas([700000, 150000], null, null, { kilos_incluidos: 5 }),
    ofrece_contraentrega: true,
    comision_recaudo: TARIFA_CERO,
    recaudo_minimo_centavos: 0,
    recaudo_maximo_centavos: 50000000,
    comision_manejo: TARIFA_CERO,
    manejo_minimo_centavos: 0,
    sin_cobertura: new Set(),
  }),
]);

/** Cierto si la transportadora entrega en esa ciudad. */
export function cubre(operador, ciudad) {
  return operador.tarifas.has(ciudad.zona) && !operador.sin_cobertura.has(ciudad.codigo_dane);
}

/** Bulto a despachar, con el valor que se declara ante la transportadora. */
export function Paquete({
  peso_gramos,
  largo_cm = 20,
  ancho_cm = 20,
  alto_cm = 15,
  valor_declarado_centavos = 0,
} = {}) {
  if (!(peso_gramos > 0)) throw new Error("el peso del paquete debe ser positivo");
  if (Math.min(largo_cm, ancho_cm, alto_cm) <= 0) {
    throw new Error("las dimensiones del paquete deben ser positivas");
  }
  if (valor_declarado_centavos < 0) throw new Error("el valor declarado no puede ser negativo");

  const centimetros_cubicos = largo_cm * ancho_cm * alto_cm;
  // Peso equivalente al espacio que ocupa la caja en el camión. El Python
  // trunca (int() de un Decimal), no redondea: aquí Math.trunc hace lo mismo.
  const peso_volumetrico_gramos =
    Math.trunc(centimetros_cubicos * _GRAMOS_POR_KILO / FACTOR_VOLUMETRICO_CM3_POR_KG);

  return Object.freeze({
    peso_gramos,
    largo_cm,
    ancho_cm,
    alto_cm,
    valor_declarado_centavos,
    peso_volumetrico_gramos,
    // El mayor entre peso real y volumétrico, con piso de un kilo.
    peso_facturable_gramos: Math.max(
      peso_gramos, peso_volumetrico_gramos, PESO_FACTURABLE_MINIMO_GRAMOS),
  });
}

/** Quita tildes y baja a minúsculas para comparar nombres escritos a mano. */
function _plegar(texto) {
  return String(texto).trim().toLowerCase().normalize("NFD").replace(/\p{Mn}/gu, "");
}

/** Encuentra la ciudad por código DANE o por nombre, con o sin tildes. */
export function resolver_ciudad(consulta) {
  const bruto = String(consulta).trim();
  if (CIUDADES.has(bruto)) return CIUDADES.get(bruto);
  const relleno = bruto.padStart(5, "0");
  if (_SOLO_DIGITOS.test(relleno) && CIUDADES.has(relleno)) return CIUDADES.get(relleno);
  const objetivo = _plegar(bruto);
  for (const ciudad of CIUDADES.values()) {
    if (_plegar(ciudad.nombre) === objetivo) return ciudad;
  }
  const parciales = buscar_ciudades(bruto);
  if (parciales.length === 1) return parciales[0];
  let msg = `no se reconoce el destino ${_repr(consulta)}`;
  if (parciales.length) {
    msg += `; quiza: ${parciales.slice(0, 5).map((c) => c.etiqueta).join(", ")}`;
  }
  throw new CiudadDesconocidaError(msg);
}

/** Sugiere ciudades cuyo nombre o departamento contiene el texto dado. */
export function buscar_ciudades(texto) {
  const objetivo = _plegar(texto);
  if (!objetivo) return [];
  return [...CIUDADES.values()].filter((c) => _plegar(c.etiqueta).includes(objetivo));
}

/**
 * Dice si el destino admite pago contra entrega y POR QUÉ no, si no.
 * Devolver el motivo importa: el agente necesita explicarle al cliente que
 * su pedido a Leticia sí sale, pero pagando por adelantado.
 */
export function diagnostico_contraentrega(destino) {
  const ciudad = typeof destino === "string" ? resolver_ciudad(destino) : destino;
  if (SIN_CONTRAENTREGA.has(ciudad.codigo_dane)) {
    return [false,
      `${ciudad.etiqueta} solo tiene acceso aereo o fluvial; la entrega final ` +
      "la hace un agente local y ninguna transportadora recauda alli"];
  }
  const disponibles = TRANSPORTADORAS
    .filter((t) => t.ofrece_contraentrega && cubre(t, ciudad))
    .map((t) => t.nombre);
  if (!disponibles.length) {
    return [false, `ninguna transportadora con recaudo cubre ${ciudad.etiqueta}`];
  }
  return [true, `disponible con ${disponibles.join(", ")}`];
}

/**
 * Monto máximo que alguna transportadora acepta recaudar en ese destino.
 * Es un límite COMERCIAL de cada operador, no una tarifa: por encima de él
 * la venta existe pero hay que cobrarla por adelantado.
 */
export function tope_contraentrega(destino) {
  const ciudad = typeof destino === "string" ? resolver_ciudad(destino) : destino;
  if (SIN_CONTRAENTREGA.has(ciudad.codigo_dane)) return 0;
  const topes = TRANSPORTADORAS
    .filter((t) => t.ofrece_contraentrega && cubre(t, ciudad))
    .map((t) => t.recaudo_maximo_centavos);
  return topes.length ? Math.max(...topes) : 0;
}

/** Cobro por peso: base más kilos adicionales redondeados HACIA ARRIBA. */
function _flete(tar, peso_gramos) {
  const kilos = Math.ceil(peso_gramos / _GRAMOS_POR_KILO);
  const adicionales = Math.max(0, kilos - tar.kilos_incluidos);
  return tar.base_centavos + adicionales * tar.adicional_por_kilo_centavos;
}

/**
 * Cotiza el despacho con todas las transportadoras que sirven el destino.
 * Con `contraentrega` activo sólo devuelve operadores que recauden y que
 * aguanten el monto: el tope de recaudo es la razón más frecuente por la que
 * un pedido grande no se puede pagar al mensajero.
 */
export function cotizar(destino, paquete, {
  contraentrega = false,
  monto_a_recaudar_centavos = 0,
} = {}) {
  const ciudad = typeof destino === "string" ? resolver_ciudad(destino) : destino;
  const peso = paquete.peso_facturable_gramos;
  const opciones = [];
  for (const operador of TRANSPORTADORAS) {
    if (!cubre(operador, ciudad)) continue;
    const notas = [];
    if (contraentrega) {
      if (!operador.ofrece_contraentrega) continue;
      if (SIN_CONTRAENTREGA.has(ciudad.codigo_dane)) continue;
      if (monto_a_recaudar_centavos > operador.recaudo_maximo_centavos) continue;
    }
    const tar = operador.tarifas.get(ciudad.zona);
    const flete = _flete(tar, peso);
    let recargo = 0;
    let dias_minimo = tar.dias_habiles_minimo;
    let dias_maximo = tar.dias_habiles_maximo;
    if (ciudad.solo_aereo) {
      recargo = aplicar_tarifa(flete, _RECARGO_AEREO_EXTRA) + _RECARGO_AEREO_FIJO;
      dias_minimo += _DIAS_EXTRA_AEREO;
      dias_maximo += _DIAS_EXTRA_AEREO;
      notas.push("carga aerea: sin via terrestre al destino");
    }
    let manejo = 0;
    if (paquete.valor_declarado_centavos > 0 && operador.comision_manejo.num > 0) {
      manejo = Math.max(
        aplicar_tarifa(paquete.valor_declarado_centavos, operador.comision_manejo),
        operador.manejo_minimo_centavos);
    }
    let recaudo = 0;
    if (contraentrega) {
      recaudo = Math.max(
        aplicar_tarifa(monto_a_recaudar_centavos, operador.comision_recaudo),
        operador.recaudo_minimo_centavos);
      notas.push(
        `recaudo contra entrega hasta ${Math.floor(operador.recaudo_maximo_centavos / 100)}`);
    }
    if (ciudad.regimen_iva_especial) notas.push("destino con regimen especial de IVA");
    opciones.push(Object.freeze({
      transportadora: operador.nombre,
      codigo_transportadora: operador.codigo,
      ciudad,
      peso_facturable_gramos: peso,
      flete_centavos: flete,
      recargo_aereo_centavos: recargo,
      manejo_centavos: manejo,
      recaudo_centavos: recaudo,
      dias_habiles_minimo: dias_minimo,
      dias_habiles_maximo: dias_maximo,
      contraentrega,
      notas,
      // Lo que el comercio paga por mover el pedido; sin sumandos ocultos.
      total_centavos: flete + recargo + manejo + recaudo,
    }));
  }
  // Array.prototype.sort es estable desde ES2019, igual que sorted() en Python.
  opciones.sort((a, b) => (a.total_centavos - b.total_centavos)
    || (a.dias_habiles_maximo - b.dias_habiles_maximo));
  return opciones;
}

/** La opción más barata, o `null` si nadie sirve el destino así. */
export function mejor_cotizacion(destino, paquete, opciones = {}) {
  const todas = cotizar(destino, paquete, opciones);
  return todas.length ? todas[0] : null;
}

/* ===================================================================== *
 *  impuesto.py — IVA colombiano: 19 %, 5 %, exento y excluido
 *
 *  EXENTO y EXCLUIDO no son sinónimos y confundirlos falsea el precio y la
 *  declaración. Un bien EXENTO (Art. 477 ET: carne, leche, huevos) está
 *  gravado a tarifa CERO, de modo que el vendedor sí conserva el derecho a
 *  descontar el IVA que pagó por sus insumos. Un bien EXCLUIDO (Art. 424:
 *  frutas frescas, panela, arroz) simplemente NO CAUSA el impuesto, y
 *  entonces el IVA de sus insumos se vuelve mayor costo y se traslada al
 *  precio. En la factura electrónica el exento viaja con una línea de IVA al
 *  0,00 % y el excluido no lleva línea de impuesto.
 * ===================================================================== */

export const TARIFA_IVA_GENERAL = tarifa(19, 100);
export const TARIFA_IVA_REDUCIDA = tarifa(5, 100);
export const TARIFA_INC_RESTAURANTES = tarifa(8, 100);

export const IMPUESTOS_SALUDABLES =
  "El IBUA sobre bebidas azucaradas (articulo 513-2 ET) y el ICUI sobre " +
  "comestibles ultraprocesados (articulo 513-6 ET) son monofasicos: se causan " +
  "en la venta del productor o en la importacion, no en el mostrador. La " +
  "tienda no los liquida; ya vienen dentro de su costo de compra.";

export const Regimen = Object.freeze({
  GRAVADO_19: "gravado_19",
  GRAVADO_5: "gravado_5",
  EXENTO: "exento",
  EXCLUIDO: "excluido",
  INC_8: "inc_8",
});

export const TRATAMIENTOS = new Map([
  [Regimen.GRAVADO_19, Object.freeze({
    regimen: Regimen.GRAVADO_19,
    tributo: "IVA",
    tarifa: TARIFA_IVA_GENERAL,
    causa_impuesto: true,
    da_derecho_a_descontables: true,
    fundamento: "Art. 468 ET",
    explicacion: "Tarifa general del impuesto sobre las ventas.",
  })],
  [Regimen.GRAVADO_5, Object.freeze({
    regimen: Regimen.GRAVADO_5,
    tributo: "IVA",
    tarifa: TARIFA_IVA_REDUCIDA,
    causa_impuesto: true,
    da_derecho_a_descontables: true,
    fundamento: "Art. 468-1 ET",
    explicacion: "Tarifa diferencial para cafe, harinas, pastas y embutidos.",
  })],
  [Regimen.EXENTO, Object.freeze({
    regimen: Regimen.EXENTO,
    tributo: "IVA",
    tarifa: TARIFA_CERO,
    causa_impuesto: true,
    da_derecho_a_descontables: true,
    fundamento: "Art. 477 ET",
    explicacion:
      "Gravado a tarifa cero: la factura lleva la linea de IVA al 0,00 por " +
      "ciento y el vendedor conserva el derecho a impuestos descontables.",
  })],
  [Regimen.EXCLUIDO, Object.freeze({
    regimen: Regimen.EXCLUIDO,
    tributo: null,
    tarifa: TARIFA_CERO,
    causa_impuesto: false,
    da_derecho_a_descontables: false,
    fundamento: "Art. 424 ET",
    explicacion:
      "No causa el impuesto: la factura no lleva linea de IVA y el IVA de " +
      "los insumos se vuelve mayor costo del producto.",
  })],
  [Regimen.INC_8, Object.freeze({
    regimen: Regimen.INC_8,
    tributo: "INC",
    tarifa: TARIFA_INC_RESTAURANTES,
    causa_impuesto: true,
    da_derecho_a_descontables: false,
    fundamento: "Art. 512-1 num. 3 ET",
    explicacion:
      "Expendio de comidas preparadas: paga impuesto nacional al consumo " +
      "del 8 por ciento y, por eso mismo, no causa IVA.",
  })],
]);

/** Línea de pedido antes de liquidar impuestos. */
export function LineaVenta(descripcion, regimen, precio_unitario_centavos,
                           cantidad = 1, descuento_centavos = 0) {
  if (!(cantidad > 0)) throw new Error(`${descripcion}: la cantidad debe ser positiva`);
  if (precio_unitario_centavos < 0) {
    throw new Error(`${descripcion}: el precio no puede ser negativo`);
  }
  const bruto = precio_unitario_centavos * cantidad;
  if (!(descuento_centavos >= 0 && descuento_centavos <= bruto)) {
    throw new Error(`${descripcion}: el descuento debe estar entre 0 y ${bruto}`);
  }
  return Object.freeze({
    descripcion,
    regimen,
    precio_unitario_centavos,
    cantidad,
    descuento_centavos,
    bruto_centavos: bruto,
  });
}

/** Aplica las dos causales que apagan el IVA sin cambiar el producto. */
function _regimen_efectivo(regimen, destino, responsable_iva) {
  const tratamiento = TRATAMIENTOS.get(regimen);
  if (tratamiento.tributo !== "IVA") return [regimen, null];
  if (destino && REGIMEN_IVA_ESPECIAL.has(destino.codigo_dane)) {
    return [Regimen.EXCLUIDO,
      `venta con destino ${destino.etiqueta}: excluida del IVA ` +
      "(Art. 423 ET / Art. 270 Ley 223 de 1995)"];
  }
  if (!responsable_iva) {
    return [Regimen.EXCLUIDO,
      "el comercio no es responsable de IVA (Art. 437 par. 3 ET), " +
      "no puede cobrarlo ni discriminarlo en la factura"];
  }
  return [regimen, null];
}

/** Liquida una línea aplicando las causales de exclusión territorial. */
export function liquidar_linea(linea, { destino = null, responsable_iva = true } = {}) {
  const [aplicado, motivo] = _regimen_efectivo(linea.regimen, destino, responsable_iva);
  const tratamiento = TRATAMIENTOS.get(aplicado);
  const base = linea.bruto_centavos - linea.descuento_centavos;
  const impuesto = tratamiento.causa_impuesto ? aplicar_tarifa(base, tratamiento.tarifa) : 0;
  return Object.freeze({
    descripcion: linea.descripcion,
    cantidad: linea.cantidad,
    regimen_solicitado: linea.regimen,
    regimen_aplicado: aplicado,
    tributo: tratamiento.tributo,
    tarifa: tratamiento.tarifa,
    bruto_centavos: linea.bruto_centavos,
    descuento_centavos: linea.descuento_centavos,
    base_gravable_centavos: base,
    impuesto_centavos: impuesto,
    fundamento: tratamiento.fundamento,
    motivo_ajuste: motivo,
    total_centavos: base + impuesto,
    da_derecho_a_descontables: tratamiento.da_derecho_a_descontables,
  });
}

/** Agrupa por tributo y tarifa conservando el orden de aparición. */
function _subtotales(lineas) {
  const acumulado = new Map();
  for (const linea of lineas) {
    if (linea.tributo === null) continue;
    const clave = `${linea.tributo}|${linea.tarifa.num}/${linea.tarifa.den}`;
    if (!acumulado.has(clave)) {
      acumulado.set(clave, { tributo: linea.tributo, tarifa: linea.tarifa, base: 0, valor: 0 });
    }
    const cubo = acumulado.get(clave);
    cubo.base += linea.base_gravable_centavos;
    cubo.valor += linea.impuesto_centavos;
  }
  return [...acumulado.values()].map((c) => Object.freeze({
    tributo: c.tributo,
    tarifa: c.tarifa,
    base_centavos: c.base,
    valor_centavos: c.valor,
    tarifa_porcentual: porcentaje(c.tarifa),
  }));
}

/**
 * Liquida un pedido completo LÍNEA POR LÍNEA y luego suma, nunca al revés:
 * la DIAN valida que el impuesto declarado en cada línea sume exactamente el
 * total del documento, y aplicar la tarifa sobre el agregado produce
 * diferencias de centavos que rechazan la factura.
 */
export function liquidar(lineas, { destino = null, responsable_iva = true } = {}) {
  const liquidadas = [...lineas].map((l) => liquidar_linea(l, { destino, responsable_iva }));
  const suma = (f) => liquidadas.reduce((a, l) => a + f(l), 0);
  const bruto = suma((l) => l.bruto_centavos);
  const descuentos = suma((l) => l.descuento_centavos);
  const base = suma((l) => l.base_gravable_centavos);
  const iva = suma((l) => (l.tributo === "IVA" ? l.impuesto_centavos : 0));
  const inc = suma((l) => (l.tributo === "INC" ? l.impuesto_centavos : 0));
  // dict.fromkeys en Python: deduplica conservando el orden de aparición.
  const notas = [...new Set(liquidadas.map((l) => l.motivo_ajuste).filter(Boolean))];
  return Object.freeze({
    lineas: liquidadas,
    subtotales: _subtotales(liquidadas),
    bruto_centavos: bruto,
    descuentos_centavos: descuentos,
    base_gravable_centavos: base,
    iva_centavos: iva,
    inc_centavos: inc,
    total_centavos: base + iva + inc,
    notas,
  });
}

/**
 * Separa la venta según si el IVA de los insumos se recupera o se pierde.
 * Es la consecuencia práctica de que exento y excluido sean cosas distintas:
 * sobre la porción excluida el IVA que la tienda pagó a su proveedor no se
 * descuenta, se vuelve costo, y si no se traslada al precio la venta pierde
 * margen sin que nadie lo note en la caja.
 */
export function resumen_descontables(liquidacion) {
  const con_derecho = liquidacion.lineas
    .filter((l) => l.da_derecho_a_descontables)
    .reduce((a, l) => a + l.base_gravable_centavos, 0);
  const sin_derecho = liquidacion.base_gravable_centavos - con_derecho;
  const nota = sin_derecho === 0
    ? "toda la venta conserva el derecho a impuestos descontables"
    : "sobre la base sin derecho el IVA pagado a proveedores no se descuenta " +
      "(Art. 488 ET) y debe absorberse en el precio de venta";
  return Object.freeze({
    base_con_derecho_centavos: con_derecho,
    base_sin_derecho_centavos: sin_derecho,
    nota,
  });
}

/* ===================================================================== *
 *  retracto.py — derecho de retracto y calendario de días hábiles
 *
 *  El Art. 47 de la Ley 1480 de 2011 le da al consumidor CINCO DÍAS HÁBILES
 *  contados desde la entrega para retractarse, pero sólo cuando la venta se
 *  hizo por métodos no tradicionales o a distancia: quien compra en el
 *  mostrador no tiene retracto. El plazo tampoco se cuenta en días corridos,
 *  y ahí está la trampa que ningún calendario genérico resuelve.
 *
 *  Colombia tiene DIECIOCHO festivos al año y la Ley 51 de 1983 (la ley
 *  Emiliani) traslada doce de ellos al lunes siguiente para producir un
 *  puente. Otros cinco se derivan de la Pascua: Jueves y Viernes Santo caen
 *  donde caen, mientras que Ascensión, Corpus Christi y Sagrado Corazón ya
 *  vienen trasladados al lunes, a 43, 64 y 71 días de la Pascua. Con Semana
 *  Santa de por medio, cinco días hábiles pueden ser once de calendario.
 *
 *  TODAS las fechas de esta sección son instantes UTC a medianoche. Nunca se
 *  usa `new Date(a, m, d)` ni `getMonth()`: en Bogotá (UTC−5) eso desplaza
 *  la fecha un día al serializar y el conteo de días hábiles se corre.
 * ===================================================================== */

const _MS_POR_DIA = 86400000;

/** Fecha civil como instante UTC a medianoche. `mes` es 1..12. */
export function fecha(anio, mes, dia) {
  return new Date(Date.UTC(anio, mes - 1, dia));
}

/** Parsea AAAA-MM-DD de forma estricta y en UTC. */
export function desde_iso(texto) {
  const m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(String(texto).trim());
  if (!m) throw new Error(`fecha invalida ${_repr(texto)}; se espera AAAA-MM-DD`);
  const f = fecha(Number(m[1]), Number(m[2]), Number(m[3]));
  if (Number.isNaN(f.getTime())) {
    throw new Error(`fecha invalida ${_repr(texto)}`);
  }
  return f;
}

/** Serializa a AAAA-MM-DD, que es como FastAPI serializa un `datetime.date`. */
export function a_iso(f) {
  return f.toISOString().slice(0, 10);
}

/** Suma días de calendario. Aritmética pura de milisegundos: sin horario de verano. */
export function sumar_dias(f, n) {
  return new Date(f.getTime() + n * _MS_POR_DIA);
}

/** Días de calendario entre dos fechas, como `(b - a).days` en Python. */
export function dias_calendario(a, b) {
  return Math.round((b.getTime() - a.getTime()) / _MS_POR_DIA);
}

/** Día de la semana con la convención de Python: lunes = 0 … domingo = 6. */
function _dia_semana(f) {
  return (f.getUTCDay() + 6) % 7;
}

function _mod(n, m) {
  return ((n % m) + m) % m;
}

const _LUNES = 0;
const _SABADO = 5;

export const DIAS_HABILES_RETRACTO = 5;              // Art. 47 Ley 1480 de 2011
export const DIAS_PARA_DEVOLVER_DINERO = 30;         // días calendario, mismo artículo

/** Festivos que NO se trasladan: caen el día que caen. */
const _FIJOS = Object.freeze([
  [1, 1, "Ano Nuevo"],
  [5, 1, "Dia del Trabajo"],
  [7, 20, "Dia de la Independencia"],
  [8, 7, "Batalla de Boyaca"],
  [12, 8, "Inmaculada Concepcion"],
  [12, 25, "Navidad"],
]);

/** Festivos que la Ley 51 de 1983 corre al lunes siguiente. */
const _TRASLADABLES = Object.freeze([
  [1, 6, "Reyes Magos"],
  [3, 19, "Dia de San Jose"],
  [6, 29, "San Pedro y San Pablo"],
  [8, 15, "Asuncion de la Virgen"],
  [10, 12, "Dia de la Raza"],
  [11, 1, "Todos los Santos"],
  [11, 11, "Independencia de Cartagena"],
]);

const _DESDE_PASCUA_FIJOS = Object.freeze([
  [-3, "Jueves Santo"],
  [-2, "Viernes Santo"],
]);

/** Ya incluyen el traslado: 39, 60 y 68 días litúrgicos corridos al lunes. */
const _DESDE_PASCUA_TRASLADADOS = Object.freeze([
  [43, "Ascension del Senor"],
  [64, "Corpus Christi"],
  [71, "Sagrado Corazon de Jesus"],
]);

export const Modalidad = Object.freeze({
  DOMICILIO: "domicilio",
  TIENDA_VIRTUAL: "tienda_virtual",
  WHATSAPP: "whatsapp",
  TELEFONO: "telefono",
  MOSTRADOR: "mostrador",
  RECOGIDA_EN_TIENDA: "recogida_en_tienda",
});

/** Ventas por métodos no tradicionales o a distancia (Art. 47 Ley 1480). */
const _MODALIDADES_A_DISTANCIA = new Set([
  Modalidad.DOMICILIO, Modalidad.TIENDA_VIRTUAL, Modalidad.WHATSAPP, Modalidad.TELEFONO,
]);

/** Excepciones del parágrafo del Art. 47: nada de esto se puede devolver. */
export const CATEGORIAS_SIN_RETRACTO = new Set([
  "perecedero",
  "personalizado",
  "servicio_iniciado",
  "uso_personal_higienico",
  "apuestas_y_loterias",
]);

/**
 * Domingo de Pascua por el algoritmo gregoriano anónimo (Meeus).
 * Todo el calendario móvil colombiano cuelga de esta fecha, así que se
 * calcula en vez de tabularse: una tabla se queda corta el año que nadie la
 * actualiza. Es el MISMO algoritmo del Python, transcrito paso a paso —
 * sustituirlo por otro cambiaría cinco festivos.
 */
export function pascua(anio) {
  const a = _mod(anio, 19);
  const b = Math.floor(anio / 100);
  const c = _mod(anio, 100);
  const d = Math.floor(b / 4);
  const e = _mod(b, 4);
  const f = Math.floor((b + 8) / 25);
  const g = Math.floor((b - f + 1) / 3);
  const h = _mod(19 * a + b - d - g + 15, 30);
  const i = Math.floor(c / 4);
  const k = _mod(c, 4);
  const ele = _mod(32 + 2 * e + 2 * i - h - k, 7);
  const m = Math.floor((a + 11 * h + 22 * ele) / 451);
  const bruto = h + ele - 7 * m + 114;
  const mes = Math.floor(bruto / 31);
  const dia = _mod(bruto, 31) + 1;
  return fecha(anio, mes, dia);
}

/** Corre la fecha al lunes siguiente; si ya es lunes, la deja igual. */
function _al_lunes_siguiente(f) {
  return sumar_dias(f, _mod(_LUNES - _dia_semana(f), 7));
}

const _CACHE_FESTIVOS = new Map();

/** Los dieciocho festivos colombianos del año, ordenados por fecha y nombre. */
export function festivos(anio) {
  if (_CACHE_FESTIVOS.has(anio)) return _CACHE_FESTIVOS.get(anio);
  const domingo_pascua = pascua(anio);
  const encontrados = [];
  for (const [mes, dia, nombre] of _FIJOS) {
    const f = fecha(anio, mes, dia);
    encontrados.push({ fecha: f, nombre, trasladado: false, fecha_original: f });
  }
  for (const [mes, dia, nombre] of _TRASLADABLES) {
    const original = fecha(anio, mes, dia);
    const movido = _al_lunes_siguiente(original);
    encontrados.push({
      fecha: movido,
      nombre,
      trasladado: movido.getTime() !== original.getTime(),
      fecha_original: original,
    });
  }
  for (const [delta, nombre] of _DESDE_PASCUA_FIJOS) {
    const f = sumar_dias(domingo_pascua, delta);
    encontrados.push({ fecha: f, nombre, trasladado: false, fecha_original: f });
  }
  for (const [delta, nombre] of _DESDE_PASCUA_TRASLADADOS) {
    encontrados.push({
      fecha: sumar_dias(domingo_pascua, delta),
      nombre,
      trasladado: true,
      fecha_original: sumar_dias(domingo_pascua, delta - 4),
    });
  }
  encontrados.sort((x, y) => (x.fecha.getTime() - y.fecha.getTime())
    || (x.nombre < y.nombre ? -1 : x.nombre > y.nombre ? 1 : 0));
  const lista = Object.freeze(encontrados.map((f) => Object.freeze({
    ...f,
    // Norma que explica por qué ese día no cuenta.
    fundamento: f.trasladado ? "Ley 51 de 1983 (traslado al lunes)" : "festivo de fecha fija",
  })));
  _CACHE_FESTIVOS.set(anio, lista);
  return lista;
}

const _INDICE_FESTIVOS = new Map();

function _indice_festivos(anio) {
  if (!_INDICE_FESTIVOS.has(anio)) {
    _INDICE_FESTIVOS.set(anio, new Set(festivos(anio).map((f) => f.fecha.getTime())));
  }
  return _INDICE_FESTIVOS.get(anio);
}

/** Cierto si la fecha es festivo nacional colombiano. */
export function es_festivo(dia) {
  return _indice_festivos(dia.getUTCFullYear()).has(dia.getTime());
}

/**
 * Cierto si el día cuenta para un término en días hábiles.
 * Por defecto el sábado NO cuenta: los términos del consumidor se surten
 * ante la SIC, que se rige por el calendario administrativo de lunes a
 * viernes (Art. 62 Ley 4 de 1913 y Art. 118 del Código General del Proceso).
 */
export function es_dia_habil(dia, { sabado_habil = false } = {}) {
  const tope = sabado_habil ? _SABADO + 1 : _SABADO;
  return _dia_semana(dia) < tope && !es_festivo(dia);
}

/**
 * Fecha del n-ésimo día hábil posterior a `inicio`.
 * El día de la entrega NO se cuenta: el término corre desde el día hábil
 * siguiente, que es como la SIC computa los plazos del consumidor.
 */
export function sumar_dias_habiles(inicio, dias, { sabado_habil = false } = {}) {
  if (dias < 0) throw new Error("no se pueden sumar dias habiles negativos");
  let cursor = inicio;
  let restantes = dias;
  while (restantes > 0) {
    cursor = sumar_dias(cursor, 1);
    if (es_dia_habil(cursor, { sabado_habil })) restantes -= 1;
  }
  return cursor;
}

/** Cuenta días hábiles en el intervalo abierto por la izquierda. */
export function dias_habiles_entre(inicio, fin, { sabado_habil = false } = {}) {
  if (fin.getTime() <= inicio.getTime()) return 0;
  let total = 0;
  let cursor = inicio;
  while (cursor.getTime() < fin.getTime()) {
    cursor = sumar_dias(cursor, 1);
    if (es_dia_habil(cursor, { sabado_habil })) total += 1;
  }
  return total;
}

/**
 * Decide si la venta admite retracto y explica el motivo.
 * El motivo es parte del resultado porque la respuesta útil para el cliente
 * no es que no, sino POR QUÉ no: una arepa no se devuelve porque es
 * perecedera, no porque la tienda no quiera.
 */
export function aplica_retracto(modalidad, { exclusiones = null } = {}) {
  const presentes = exclusiones ? [...exclusiones] : [];
  const desconocidas = presentes.filter((x) => !CATEGORIAS_SIN_RETRACTO.has(x)).sort();
  if (desconocidas.length) {
    throw new Error(
      `exclusiones de retracto no reconocidas: [${desconocidas.map(_repr).join(", ")}]`);
  }
  if (!_MODALIDADES_A_DISTANCIA.has(modalidad)) {
    return [false,
      "el retracto del Art. 47 de la Ley 1480 de 2011 solo cubre ventas por " +
      "metodos no tradicionales o a distancia; esta se celebro en el punto de venta"];
  }
  if (presentes.length) {
    return [false, `el paragrafo del Art. 47 excluye del retracto: ${presentes.slice().sort().join(", ")}`];
  }
  return [true, "venta a distancia sin bienes exceptuados: el retracto aplica"];
}

/** Calcula el plazo de retracto de una entrega concreta. */
export function ventana_retracto(fecha_entrega, {
  modalidad = Modalidad.DOMICILIO,
  exclusiones = null,
  sabado_habil = false,
} = {}) {
  const [aplica, motivo] = aplica_retracto(modalidad, { exclusiones });
  if (!aplica) {
    return Object.freeze({
      aplica: false,
      motivo,
      fecha_entrega,
      inicio: null,
      vence: null,
      dias_habiles: 0,
      festivos_intermedios: [],
      dias_para_devolver_dinero: DIAS_PARA_DEVOLVER_DINERO,
      vigente: () => false,
      dias_habiles_restantes: () => 0,
    });
  }
  const inicio = sumar_dias_habiles(fecha_entrega, 1, { sabado_habil });
  const vence = sumar_dias_habiles(fecha_entrega, DIAS_HABILES_RETRACTO, { sabado_habil });
  const intermedios = [];
  for (let anio = fecha_entrega.getUTCFullYear(); anio <= vence.getUTCFullYear(); anio += 1) {
    for (const f of festivos(anio)) {
      if (f.fecha.getTime() >= fecha_entrega.getTime() && f.fecha.getTime() <= vence.getTime()) {
        intermedios.push(f);
      }
    }
  }
  return Object.freeze({
    aplica: true,
    motivo,
    fecha_entrega,
    inicio,
    vence,
    dias_habiles: DIAS_HABILES_RETRACTO,
    festivos_intermedios: intermedios,
    dias_para_devolver_dinero: DIAS_PARA_DEVOLVER_DINERO,
    /** Cierto si en `hoy` el cliente todavía puede retractarse. */
    vigente: (hoy) => hoy.getTime() <= vence.getTime(),
    /** Cuántos días hábiles le quedan al cliente contados desde `hoy`. */
    dias_habiles_restantes: (hoy, opciones = {}) => (
      hoy.getTime() > vence.getTime()
        ? 0
        : dias_habiles_entre(hoy, vence, opciones) + 1),
  });
}

/* ===================================================================== *
 *  pago.py — qué rieles de pago aplican a un pedido colombiano concreto
 *
 *  En Colombia el medio de pago no es una preferencia del cliente sino una
 *  función del destino, del monto y de lo que va en el carrito. El contra
 *  entrega, que es el riel dominante fuera de las capitales, tiene tope de
 *  recaudo, cobertura parcial y NO EXISTE donde sólo llega el avión. Nequi
 *  es un depósito de bajo monto y por norma no puede mover más de ocho
 *  salarios mínimos. PSE necesita que el cliente escoja banco antes de
 *  empezar. La tarjeta arrastra retención en la fuente del 1,5 % contra el
 *  comercio, y todo lo que termina en una cuenta paga el cuatro por mil.
 *
 *  Por eso la herramienta no ofrece una lista fija de botones: evalúa,
 *  descarta y explica.
 * ===================================================================== */

/** Gravamen a los movimientos financieros, el cuatro por mil (Art. 870 ET). */
export const TARIFA_GMF = tarifa(4, 1000);

/** Retiros mensuales exentos de GMF en una cuenta marcada (Art. 879 num. 1 ET). */
export const UVT_EXENTAS_GMF_MENSUALES = 65;

/** Retención en la fuente sobre pagos con tarjeta, sobre la base sin IVA. */
export const TARIFA_RETEFUENTE_TARJETAS = tarifa(15, 1000);

/** Tope en salarios mínimos de un depósito de bajo monto (Decreto 2555 de 2010).
 *  Es el techo regulatorio de Nequi y de los demás depósitos electrónicos: por
 *  eso un pedido grande no se puede pagar por ahí aunque el cliente quiera. */
export const SMMLV_TOPE_DEPOSITO_BAJO_MONTO = 8;

const _CUOTAS_MAXIMAS_TARJETA = 36;
const _DIAS_LIQUIDACION_CONTRAENTREGA = 8;

/**
 * Valores que el Gobierno reajusta cada año.
 * Van en un objeto y no en constantes sueltas porque cambian por decreto en
 * diciembre: si estuvieran incrustados en la lógica, el sistema empezaría el
 * año calculando topes viejos sin que nadie se entere.
 */
export function ParametrosFiscales(anio, uvt_centavos, smmlv_centavos) {
  return Object.freeze({
    anio,
    uvt_centavos,
    smmlv_centavos,
    tope_deposito_bajo_monto_centavos: SMMLV_TOPE_DEPOSITO_BAJO_MONTO * smmlv_centavos,
    exencion_gmf_mensual_centavos: UVT_EXENTAS_GMF_MENSUALES * uvt_centavos,
  });
}

/** Últimos valores verificados. Actualizar con el decreto anual de UVT y salario mínimo. */
export const PARAMETROS_VIGENTES = ParametrosFiscales(2025, 4979900, 142350000);

/** Entidades habilitadas en PSE que un cliente de tienda de barrio suele tener. */
export const BANCOS_PSE = new Set([
  "bancolombia",
  "davivienda",
  "banco de bogota",
  "bbva colombia",
  "banco de occidente",
  "banco popular",
  "banco caja social",
  "scotiabank colpatria",
  "itau",
  "banco av villas",
  "banco agrario",
  "banco falabella",
  "banco pichincha",
  "banco gnb sudameris",
  "banco serfinanza",
  "bancoomeva",
  "lulo bank",
  "nequi",
  "daviplata",
]);

export const MetodoPago = Object.freeze({
  NEQUI: "nequi",
  PSE: "pse",
  BANCOLOMBIA: "bancolombia",
  TARJETA: "tarjeta",
  CONTRAENTREGA: "contraentrega",
});

const _NOMBRES_PAGO = new Map([
  [MetodoPago.NEQUI, "Nequi"],
  [MetodoPago.PSE, "PSE (debito de cuenta bancaria)"],
  [MetodoPago.BANCOLOMBIA, "Transferencia Bancolombia"],
  [MetodoPago.TARJETA, "Tarjeta debito o credito"],
  [MetodoPago.CONTRAENTREGA, "Contra entrega (efectivo al mensajero)"],
]);

/** Todo lo que condiciona la disponibilidad de un riel. */
export function ContextoPago({
  total_centavos,
  ciudad,
  base_sin_impuestos_centavos = 0,
  comision_recaudo_centavos = 0,
  contiene_servicios = false,
  banco_pse = null,
  cliente_tiene_bancolombia = false,
  parametros = PARAMETROS_VIGENTES,
} = {}) {
  if (!(total_centavos > 0)) throw new Error("el total del pedido debe ser positivo");
  return Object.freeze({
    total_centavos,
    ciudad,
    base_sin_impuestos_centavos,
    comision_recaudo_centavos,
    contiene_servicios,
    banco_pse,
    cliente_tiene_bancolombia,
    parametros,
    // Base de la retención: el valor de la venta sin impuestos.
    base_retefuente_centavos: base_sin_impuestos_centavos || total_centavos,
  });
}

/** Cuatro por mil sobre un movimiento financiero. */
export function gmf(monto) {
  return aplicar_tarifa(monto, TARIFA_GMF);
}

/** Comisión de pasarela con su IVA, que también lo asume el comercio. */
function _comision(base, porcentual, fijo) {
  const bruta = aplicar_tarifa(base, porcentual) + fijo;
  return bruta + aplicar_tarifa(bruta, TARIFA_IVA_GENERAL);
}

/** Cierra las cuentas de un riel una vez decidida su disponibilidad. */
function _armar(metodo, contexto, {
  motivos, comision, retencion = 0, recargo_cliente = 0,
  dias = 0, cuotas = 1, requisitos = [], notas = [],
}) {
  const disponible = motivos.length === 0;
  const total_cliente = contexto.total_centavos + recargo_cliente;
  const bruto_comercio = total_cliente - comision - retencion;
  const impuesto_movimiento = disponible ? gmf(bruto_comercio) : 0;
  return Object.freeze({
    metodo,
    nombre: _NOMBRES_PAGO.get(metodo),
    disponible,
    motivos,
    requisitos,
    recargo_cliente_centavos: recargo_cliente,
    comision_centavos: comision,
    retencion_centavos: retencion,
    gmf_centavos: impuesto_movimiento,
    dias_habiles_liquidacion: dias,
    cuotas_maximas: cuotas,
    total_cliente_centavos: total_cliente,
    neto_comercio_centavos: bruto_comercio - impuesto_movimiento,
    notas,
    // Suma de comisión, retención y GMF: lo que se pierde por el camino.
    costo_total_comercio_centavos: comision + retencion + impuesto_movimiento,
  });
}

/** Nequi: instantáneo, barato y con techo regulatorio. */
function _evaluar_nequi(contexto) {
  const motivos = [];
  const tope = contexto.parametros.tope_deposito_bajo_monto_centavos;
  if (contexto.total_centavos > tope) {
    motivos.push(
      "Nequi es un deposito de bajo monto y no admite mas de " +
      `${SMMLV_TOPE_DEPOSITO_BAJO_MONTO} salarios minimos por operacion ` +
      "(Decreto 2555 de 2010); el pedido los supera");
  }
  return _armar(MetodoPago.NEQUI, contexto, {
    motivos,
    comision: _comision(contexto.total_centavos, tarifa(15, 1000), 0),
    dias: 0,
    requisitos: ["numero de celular del cliente"],
    notas: ["acreditacion inmediata: el pedido se despacha el mismo dia"],
  });
}

/** PSE: débito directo de cuenta, exige escoger banco de antemano. */
function _evaluar_pse(contexto) {
  const motivos = [];
  if (contexto.banco_pse === null || contexto.banco_pse === undefined) {
    motivos.push("PSE exige que el cliente elija su banco antes de iniciar el debito");
  } else if (!BANCOS_PSE.has(_plegar(contexto.banco_pse))) {
    motivos.push(`el banco ${_repr(contexto.banco_pse)} no esta habilitado en PSE`);
  }
  if (contexto.total_centavos < 150000) {
    motivos.push("PSE no procesa transacciones por debajo de mil quinientos pesos");
  }
  return _armar(MetodoPago.PSE, contexto, {
    motivos,
    comision: _comision(contexto.total_centavos, TARIFA_CERO, 150000),
    dias: 1,
    requisitos: ["banco del cliente", "clave de banca virtual"],
    notas: ["comision fija: es el riel mas barato para pedidos grandes"],
  });
}

/** Botón Bancolombia: transferencia entre cuentas de la misma entidad. */
function _evaluar_bancolombia(contexto) {
  const motivos = [];
  if (!contexto.cliente_tiene_bancolombia) {
    motivos.push("la transferencia directa requiere que el cliente tenga cuenta Bancolombia");
  }
  return _armar(MetodoPago.BANCOLOMBIA, contexto, {
    motivos,
    comision: _comision(contexto.total_centavos, TARIFA_CERO, 120000),
    dias: 0,
    requisitos: ["cuenta Bancolombia del cliente"],
    notas: ["transferencia entre cuentas de la misma entidad: se acredita al instante"],
  });
}

/** Tarjeta: el único riel con cuotas, y el más caro para el comercio. */
function _evaluar_tarjeta(contexto) {
  const motivos = [];
  if (contexto.total_centavos < 200000) {
    motivos.push("las franquicias no autorizan compras por debajo de dos mil pesos");
  }
  const retencion = aplicar_tarifa(contexto.base_retefuente_centavos, TARIFA_RETEFUENTE_TARJETAS);
  return _armar(MetodoPago.TARJETA, contexto, {
    motivos,
    comision: _comision(contexto.total_centavos, tarifa(299, 10000), 90000),
    retencion,
    dias: 2,
    cuotas: _CUOTAS_MAXIMAS_TARJETA,
    requisitos: ["numero de tarjeta", "autenticacion 3-D Secure"],
    notas: [
      "el adquiriente practica retencion en la fuente del 1,5 por ciento " +
      "sobre la venta sin impuestos; es un anticipo de renta, no un costo perdido",
      `admite hasta ${_CUOTAS_MAXIMAS_TARJETA} cuotas`,
    ],
  });
}

/** Contra entrega: el riel dominante, y el que más restricciones tiene. */
function _evaluar_contraentrega(contexto) {
  const motivos = [];
  if (contexto.contiene_servicios) {
    motivos.push("el contra entrega necesita un bulto fisico que entregar");
  }
  const [cubierto, detalle] = diagnostico_contraentrega(contexto.ciudad);
  if (!cubierto) motivos.push(detalle);
  const tope = tope_contraentrega(contexto.ciudad);
  if (cubierto && contexto.total_centavos > tope) {
    motivos.push(
      `ninguna transportadora que cubra ${contexto.ciudad.etiqueta} recauda mas de ` +
      `${formatear_cop(tope)}; este pedido debe cobrarse por adelantado`);
  }
  if (contexto.comision_recaudo_centavos <= 0 && cubierto) {
    motivos.push("falta cotizar el recaudo con la transportadora antes de ofrecer contra entrega");
  }
  return _armar(MetodoPago.CONTRAENTREGA, contexto, {
    motivos,
    comision: 0,
    recargo_cliente: redondear_efectivo(contexto.comision_recaudo_centavos),
    dias: _DIAS_LIQUIDACION_CONTRAENTREGA,
    requisitos: ["direccion exacta", "telefono de contacto", "efectivo al recibir"],
    notas: [
      "el valor a recaudar se redondea a los cincuenta pesos mas cercanos " +
      "porque el mensajero no da cambio por debajo de esa moneda",
      "la transportadora gira el recaudo despues de entregar: el dinero " +
      "entra dias despues de despachar el pedido",
    ],
  });
}

const _EVALUADORES = new Map([
  [MetodoPago.NEQUI, _evaluar_nequi],
  [MetodoPago.PSE, _evaluar_pse],
  [MetodoPago.BANCOLOMBIA, _evaluar_bancolombia],
  [MetodoPago.TARJETA, _evaluar_tarjeta],
  [MetodoPago.CONTRAENTREGA, _evaluar_contraentrega],
]);

/**
 * Evalúa los cinco rieles y los ordena por lo que le queda al comercio.
 * Devuelve TAMBIÉN los que no aplican, con su motivo: el agente necesita
 * poder decir por qué no aparece el contra entrega, no sólo omitirlo.
 */
export function evaluar(contexto) {
  const resultados = [..._EVALUADORES.values()].map((evaluador) => evaluador(contexto));
  resultados.sort((a, b) => {
    const da = a.disponible ? 0 : 1;
    const db = b.disponible ? 0 : 1;
    if (da !== db) return da - db;
    if (a.neto_comercio_centavos !== b.neto_comercio_centavos) {
      return b.neto_comercio_centavos - a.neto_comercio_centavos;
    }
    return a.dias_habiles_liquidacion - b.dias_habiles_liquidacion;
  });
  return resultados;
}

/** El mejor riel disponible; falla si ninguno aplica. */
export function recomendar(contexto) {
  for (const evaluacion of evaluar(contexto)) {
    if (evaluacion.disponible) return evaluacion;
  }
  throw new MetodoPagoError(
    `ningun medio de pago aplica a un pedido a ${contexto.ciudad.etiqueta}`);
}

/* ===================================================================== *
 *  catalogo.py — catálogo de una microempresa real de barrio en Medellín
 *
 *  Surtitienda La Milagrosa es una tienda de Manrique que vende abarrotes,
 *  fruver y almuerzo. Se modela así, y no como una tienda de camisetas,
 *  porque una canasta de tienda colombiana atraviesa los CINCO tratamientos
 *  a la vez: el plátano está excluido, la leche exenta, el café al cinco por
 *  ciento, el jabón al diecinueve y el almuerzo paga impuesto al consumo en
 *  vez de IVA. Un carrito de siete líneas ya obliga a liquidar cinco
 *  regímenes distintos.
 *
 *  Los precios son bases SIN impuestos: el precio de góndola se calcula por
 *  destino, porque en San Andrés y en Leticia la misma referencia no causa IVA.
 * ===================================================================== */

export const Categoria = Object.freeze({
  FRUVER: "fruver",
  LACTEOS_Y_HUEVOS: "lacteos_y_huevos",
  CARNICOS: "carnicos",
  ABARROTES: "abarrotes",
  CAFE_Y_CACAO: "cafe_y_cacao",
  PANADERIA: "panaderia",
  ASEO: "aseo",
  BEBIDAS: "bebidas",
  MASCOTAS: "mascotas",
  COMIDA_PREPARADA: "comida_preparada",
});

/** Microempresa de ejemplo; el NIT es ficticio pero su DV es real. */
export const COMERCIO = Object.freeze({
  nombre: "Surtitienda La Milagrosa S.A.S.",
  documento: Documento.parse(TipoDocumento.NIT, "900123456-8"),
  direccion: "Carrera 45 # 67-23, barrio Manrique",
  ciudad_codigo_dane: "05001",
  responsable_iva: true,
  correo: "pedidos@lamilagrosa.example.co",
});

const _PERECEDERO = ["perecedero"];
const _ART_424 = "Art. 424 ET: bien excluido del IVA";
const _ART_477 = "Art. 477 ET: bien exento, gravado a tarifa cero";
const _ART_468_1 = "Art. 468-1 ET: tarifa diferencial del cinco por ciento";
const _ART_468 = "Art. 468 ET: tarifa general del diecinueve por ciento";
const _ART_512_1 = "Art. 512-1 num. 3 ET: expendio de comidas, impuesto al consumo";

function _p(sku, nombre, categoria, regimen, precio, peso, dimensiones, fundamento,
            { exclusiones = [], servicio = false, saludable = false } = {}) {
  const [largo, ancho, alto] = dimensiones;
  return [sku, Object.freeze({
    sku,
    nombre,
    categoria,
    regimen,
    precio_base_centavos: precio,
    peso_gramos: peso,
    largo_cm: largo,
    ancho_cm: ancho,
    alto_cm: alto,
    fundamento,
    exclusiones_retracto: new Set(exclusiones),
    es_servicio: servicio,
    impuesto_saludable_incorporado: saludable,
  })];
}

export const CATALOGO = new Map([
  _p("FRU-PLA-LB", "Platano maduro (libra)", Categoria.FRUVER, Regimen.EXCLUIDO,
    280000, 500, [20, 12, 8], _ART_424, { exclusiones: _PERECEDERO }),
  _p("FRU-TOM-LB", "Tomate chonto (libra)", Categoria.FRUVER, Regimen.EXCLUIDO,
    350000, 500, [18, 14, 10], _ART_424, { exclusiones: _PERECEDERO }),
  _p("FRU-AGU-UN", "Aguacate hass (unidad)", Categoria.FRUVER, Regimen.EXCLUIDO,
    450000, 280, [12, 10, 10], _ART_424, { exclusiones: _PERECEDERO }),
  _p("FRU-PAP-LB", "Papa pastusa (libra)", Categoria.FRUVER, Regimen.EXCLUIDO,
    220000, 500, [18, 14, 10], _ART_424, { exclusiones: _PERECEDERO }),
  _p("ABA-PAN-500", "Panela redonda 500 g", Categoria.ABARROTES, Regimen.EXCLUIDO,
    420000, 520, [14, 14, 5], _ART_424),
  _p("ABA-ARR-500", "Arroz blanco 500 g", Categoria.ABARROTES, Regimen.EXCLUIDO,
    340000, 500, [18, 11, 5], _ART_424),
  _p("PAN-ARE-X5", "Arepa de maiz para asar x5", Categoria.PANADERIA, Regimen.EXCLUIDO,
    480000, 600, [16, 16, 6], _ART_424, { exclusiones: _PERECEDERO }),
  _p("LAC-HUE-X30", "Huevos AA x30", Categoria.LACTEOS_Y_HUEVOS, Regimen.EXENTO,
    1850000, 1800, [30, 30, 8], _ART_477, { exclusiones: _PERECEDERO }),
  _p("LAC-LEC-1L", "Leche entera bolsa 1 L", Categoria.LACTEOS_Y_HUEVOS, Regimen.EXENTO,
    430000, 1030, [18, 10, 8], _ART_477, { exclusiones: _PERECEDERO }),
  _p("LAC-QUE-250", "Queso campesino 250 g", Categoria.LACTEOS_Y_HUEVOS, Regimen.EXENTO,
    980000, 260, [12, 10, 6], _ART_477, { exclusiones: _PERECEDERO }),
  _p("CAR-RES-500", "Carne de res molida 500 g", Categoria.CARNICOS, Regimen.EXENTO,
    1450000, 520, [18, 12, 5], _ART_477, { exclusiones: _PERECEDERO }),
  _p("CAR-POL-500", "Pechuga de pollo 500 g", Categoria.CARNICOS, Regimen.EXENTO,
    1190000, 520, [20, 12, 5], _ART_477, { exclusiones: _PERECEDERO }),
  _p("CAF-TOS-250", "Cafe tostado molido de Antioquia 250 g", Categoria.CAFE_Y_CACAO,
    Regimen.GRAVADO_5, 1420000, 260, [14, 9, 5], _ART_468_1),
  _p("CAF-CHO-500", "Chocolate de mesa 500 g", Categoria.CAFE_Y_CACAO, Regimen.GRAVADO_5,
    915000, 520, [16, 10, 6], _ART_468_1),
  _p("ABA-PAS-500", "Pasta espagueti 500 g", Categoria.ABARROTES, Regimen.GRAVADO_5,
    370000, 500, [26, 8, 5], _ART_468_1),
  _p("ABA-HAR-500", "Harina de trigo 500 g", Categoria.ABARROTES, Regimen.GRAVADO_5,
    305000, 500, [18, 11, 5], _ART_468_1),
  _p("CAR-SAL-250", "Salchichon cervecero 250 g", Categoria.CARNICOS, Regimen.GRAVADO_5,
    847500, 260, [22, 7, 7], _ART_468_1, { exclusiones: _PERECEDERO }),
  _p("ASE-JAB-X3", "Jabon de barra x3", Categoria.ASEO, Regimen.GRAVADO_19,
    790000, 450, [18, 9, 6], _ART_468),
  _p("ASE-PAP-X4", "Papel higienico x4 rollos", Categoria.ASEO, Regimen.GRAVADO_19,
    730000, 480, [24, 24, 12], _ART_468),
  _p("ASE-DET-1K", "Detergente en polvo 1 kg", Categoria.ASEO, Regimen.GRAVADO_19,
    1050000, 1050, [22, 14, 7], _ART_468),
  _p("BEB-GAS-15", "Gaseosa 1,5 L", Categoria.BEBIDAS, Regimen.GRAVADO_19,
    455000, 1600, [10, 10, 33], _ART_468, { saludable: true }),
  _p("ABA-GAL-300", "Galletas dulces 300 g", Categoria.ABARROTES, Regimen.GRAVADO_19,
    570000, 320, [20, 12, 6], _ART_468, { saludable: true }),
  _p("MAS-CON-2K", "Concentrado para perro adulto 2 kg", Categoria.MASCOTAS, Regimen.GRAVADO_19,
    2430000, 2100, [30, 20, 10], _ART_468),
  _p("PRE-ALM-COR", "Almuerzo corrientazo del dia", Categoria.COMIDA_PREPARADA, Regimen.INC_8,
    1480000, 700, [20, 20, 8], _ART_512_1,
    { exclusiones: ["perecedero", "servicio_iniciado"], servicio: true }),
]);

/** Convierte la referencia en una línea liquidable. */
export function linea_venta(producto, cantidad = 1) {
  return LineaVenta(producto.nombre, producto.regimen, producto.precio_base_centavos, cantidad);
}

/** Todo el catálogo en orden estable. */
export function productos() {
  return [...CATALOGO.values()];
}

/** Busca por SKU exacto; falla si no existe. */
export function obtener(sku) {
  const clave = String(sku).trim().toUpperCase();
  if (!CATALOGO.has(clave)) {
    throw new ProductoDesconocidoError(
      `el SKU ${_repr(sku)} no existe en el catalogo`);
  }
  return CATALOGO.get(clave);
}

/** Busca por nombre o categoría, tolerando tildes y mayúsculas. */
export function buscar(texto) {
  const objetivo = _plegar(texto);
  if (!objetivo) return [];
  return productos().filter(
    (p) => _plegar(p.nombre).includes(objetivo) || _plegar(p.categoria).includes(objetivo));
}

/** Referencias de una sección de la tienda. */
export function por_categoria(categoria) {
  return productos().filter((p) => p.categoria === categoria);
}

/**
 * Precio de góndola con impuestos, redondeado a la moneda más pequeña.
 * Depende del destino A PROPÓSITO: la misma referencia vale menos en San
 * Andrés o en Leticia porque allí la venta no causa IVA.
 */
export function precio_al_publico(producto, {
  destino = null, responsable_iva = true, redondear = true,
} = {}) {
  const liquidada = liquidar_linea(linea_venta(producto, 1), { destino, responsable_iva });
  return redondear ? redondear_efectivo(liquidada.total_centavos) : liquidada.total_centavos;
}

/** Pedido en construcción, con lo que necesitan flete, IVA y retracto. */
export function Carrito(lineas) {
  for (const linea of lineas) {
    if (!(linea.cantidad > 0)) {
      throw new Error(`${linea.producto.sku}: la cantidad debe ser positiva`);
    }
  }
  const despachables = lineas.filter((l) => !l.producto.es_servicio);
  const exclusiones = new Set();
  for (const linea of lineas) {
    for (const causal of linea.producto.exclusiones_retracto) exclusiones.add(causal);
  }
  return Object.freeze({
    lineas: Object.freeze(lineas.slice()),
    despachables: Object.freeze(despachables),
    peso_gramos: lineas.reduce((a, l) => a + l.producto.peso_gramos * l.cantidad, 0),
    contiene_servicios: lineas.some((l) => l.producto.es_servicio),
    exclusiones_retracto: exclusiones,
    lleva_impuestos_saludables: lineas.some((l) => l.producto.impuesto_saludable_incorporado),
    /** Un carrito de sólo almuerzos existe y se factura, pero no se despacha. */
    tiene_despachables: despachables.length > 0,
    lineas_venta: () => lineas.map((l) => linea_venta(l.producto, l.cantidad)),
    /** Bulto equivalente del pedido: caja más ancha y altura apilada. */
    paquete: ({ valor_declarado_centavos = 0 } = {}) => {
      if (!despachables.length) throw new Error("el pedido no tiene nada fisico que despachar");
      return Paquete({
        peso_gramos: despachables.reduce((a, l) => a + l.producto.peso_gramos * l.cantidad, 0),
        largo_cm: Math.max(...despachables.map((l) => l.producto.largo_cm)),
        ancho_cm: Math.max(...despachables.map((l) => l.producto.ancho_cm)),
        alto_cm: despachables.reduce((a, l) => a + l.producto.alto_cm * l.cantidad, 0),
        valor_declarado_centavos,
      });
    },
  });
}

/** Construye un carrito desde pares de SKU y cantidad. */
export function armar_carrito(items) {
  const pares = items instanceof Map ? [...items.entries()]
    : Array.isArray(items) ? items
      : Object.entries(items);
  return Carrito(pares.map(([sku, cantidad]) => ({ producto: obtener(sku), cantidad })));
}

/* ===================================================================== *
 *  api.py — las seis capacidades, serializadas
 *
 *  Esta sección es el equivalente exacto de `src/tendero/api.py`, que en el
 *  backend es una capa HTTP delgada: no decide NADA. Ninguna tarifa, ningún
 *  tope, ninguna causal de exclusión y ningún redondeo viven aquí; cada
 *  cifra la calculó el dominio de arriba. Lo único que hace es resolver
 *  texto a objetos y darle forma al resultado.
 *
 *  La única aritmética es sumar mercancía más flete para armar el total que
 *  se cobra, y esa suma es legítima sin volver a liquidar impuesto porque el
 *  transporte nacional de carga está excluido del IVA (FLETE_EXCLUIDO_DE_IVA).
 *
 *  Cada función `buscar_productos`, `cotizar_envio`, … corresponde uno a uno
 *  con la herramienta WebMCP del mismo nombre y con el endpoint
 *  `POST /api/<nombre>` del backend. Devuelven la MISMA forma JSON, de modo
 *  que la vitrina pinta igual con servidor o sin él.
 * ===================================================================== */

export const VERSION = "0.1.0";

const _LIMITE_BUSQUEDA_MAXIMO = 100;
const _LIMITE_BUSQUEDA_POR_DEFECTO = 24;

/** Dinero en la única forma en que el dominio lo maneja, más su texto.
 *  Se mandan las dos: el entero para que el agente pueda comparar y sumar,
 *  y el texto ya formateado para que la página lo pinte sin reimplementar
 *  el formateo colombiano. */
function _monto(valor) {
  return { centavos: valor, texto: formatear_cop(valor) };
}

/** Tarifa como la imprime una factura colombiana: coma decimal. */
function _pct(tar) {
  return `${porcentaje(tar)} %`;
}

function _ciudad_dto(ciudad) {
  return {
    codigo_dane: ciudad.codigo_dane,
    nombre: ciudad.nombre,
    departamento: ciudad.departamento,
    etiqueta: ciudad.etiqueta,
    zona: ciudad.zona,
    solo_aereo: ciudad.solo_aereo,
    regimen_iva_especial: ciudad.regimen_iva_especial,
  };
}

/** Arma el carrito del dominio; los SKU malos los rechaza el dominio. */
function _carrito(items) {
  return armar_carrito((items || []).map((it) => [it.sku, it.cantidad ?? 1]));
}

/** Resuelve un destino opcional escrito por una persona o por un agente. */
function _ciudad(consulta) {
  if (consulta === null || consulta === undefined || !String(consulta).trim()) return null;
  return resolver_ciudad(consulta);
}

function _producto_dto(producto, destino) {
  const tratamiento = TRATAMIENTOS.get(producto.regimen);
  return {
    sku: producto.sku,
    nombre: producto.nombre,
    categoria: producto.categoria,
    regimen: producto.regimen,
    tributo: tratamiento.tributo,
    tarifa: _pct(tratamiento.tarifa),
    fundamento: producto.fundamento,
    explicacion: tratamiento.explicacion,
    precio_base: _monto(producto.precio_base_centavos),
    precio_publico: _monto(precio_al_publico(producto, { destino })),
    peso_gramos: producto.peso_gramos,
    es_servicio: producto.es_servicio,
    exclusiones_retracto: [...producto.exclusiones_retracto].sort(),
    impuesto_saludable_incorporado: producto.impuesto_saludable_incorporado,
  };
}

function _opcion_dto(cotizacion) {
  return {
    transportadora: cotizacion.transportadora,
    codigo_transportadora: cotizacion.codigo_transportadora,
    flete: _monto(cotizacion.flete_centavos),
    recargo_aereo: _monto(cotizacion.recargo_aereo_centavos),
    manejo: _monto(cotizacion.manejo_centavos),
    recaudo: _monto(cotizacion.recaudo_centavos),
    total: _monto(cotizacion.total_centavos),
    dias_habiles_minimo: cotizacion.dias_habiles_minimo,
    dias_habiles_maximo: cotizacion.dias_habiles_maximo,
    contraentrega: cotizacion.contraentrega,
    notas: [...cotizacion.notas],
  };
}

function _metodo_dto(evaluacion) {
  return {
    metodo: evaluacion.metodo,
    nombre: evaluacion.nombre,
    disponible: evaluacion.disponible,
    motivos: [...evaluacion.motivos],
    requisitos: [...evaluacion.requisitos],
    recargo_cliente: _monto(evaluacion.recargo_cliente_centavos),
    comision: _monto(evaluacion.comision_centavos),
    retencion: _monto(evaluacion.retencion_centavos),
    gmf: _monto(evaluacion.gmf_centavos),
    costo_total_comercio: _monto(evaluacion.costo_total_comercio_centavos),
    total_cliente: _monto(evaluacion.total_cliente_centavos),
    neto_comercio: _monto(evaluacion.neto_comercio_centavos),
    dias_habiles_liquidacion: evaluacion.dias_habiles_liquidacion,
    cuotas_maximas: evaluacion.cuotas_maximas,
    notas: [...evaluacion.notas],
  };
}

function _liquidacion_dto(liquidacion, carrito, destino, responsable_iva) {
  const resumen = resumen_descontables(liquidacion);
  const saludables = carrito.lleva_impuestos_saludables;
  return {
    destino: destino ? _ciudad_dto(destino) : null,
    responsable_iva,
    lineas: liquidacion.lineas.map((linea) => ({
      descripcion: linea.descripcion,
      cantidad: linea.cantidad,
      regimen_solicitado: linea.regimen_solicitado,
      regimen_aplicado: linea.regimen_aplicado,
      tributo: linea.tributo,
      tarifa: _pct(linea.tarifa),
      bruto: _monto(linea.bruto_centavos),
      descuento: _monto(linea.descuento_centavos),
      base_gravable: _monto(linea.base_gravable_centavos),
      impuesto: _monto(linea.impuesto_centavos),
      total: _monto(linea.total_centavos),
      fundamento: linea.fundamento,
      motivo_ajuste: linea.motivo_ajuste,
      da_derecho_a_descontables: linea.da_derecho_a_descontables,
    })),
    subtotales: liquidacion.subtotales.map((s) => ({
      tributo: s.tributo,
      tarifa: `${s.tarifa_porcentual} %`,
      base: _monto(s.base_centavos),
      valor: _monto(s.valor_centavos),
    })),
    bruto: _monto(liquidacion.bruto_centavos),
    descuentos: _monto(liquidacion.descuentos_centavos),
    base_gravable: _monto(liquidacion.base_gravable_centavos),
    iva: _monto(liquidacion.iva_centavos),
    inc: _monto(liquidacion.inc_centavos),
    total: _monto(liquidacion.total_centavos),
    notas: [...liquidacion.notas],
    descontables: {
      base_con_derecho: _monto(resumen.base_con_derecho_centavos),
      base_sin_derecho: _monto(resumen.base_sin_derecho_centavos),
      nota: resumen.nota,
    },
    lleva_impuestos_saludables: saludables,
    nota_impuestos_saludables: saludables ? IMPUESTOS_SALUDABLES : null,
  };
}

/** Latido con el tamaño de los maestros cargados. Equivale a `GET /health`. */
export function salud() {
  return {
    estado: "ok",
    version: VERSION,
    productos: CATALOGO.size,
    ciudades: CIUDADES.size,
    transportadoras: TRANSPORTADORAS.length,
    sin_contraentrega: SIN_CONTRAENTREGA.size,
  };
}

/** Maestros de arranque de la vitrina. Equivale a `GET /api/contexto`. */
export function contexto() {
  return {
    comercio: {
      nombre: COMERCIO.nombre,
      documento: COMERCIO.documento.toString(),
      codigo_dian: COMERCIO.documento.codigo_dian,
      direccion: COMERCIO.direccion,
      ciudad: CIUDADES.get(COMERCIO.ciudad_codigo_dane).etiqueta,
      responsable_iva: COMERCIO.responsable_iva,
      correo: COMERCIO.correo,
    },
    categorias: Object.values(Categoria),
    ciudades: [...CIUDADES.values()].map(_ciudad_dto),
    tipos_documento: [...REGLAS.values()].map((regla) => ({
      tipo: regla.tipo,
      codigo_dian: regla.codigo_dian,
      nombre: regla.nombre,
      largo_minimo: regla.largo_minimo,
      largo_maximo: regla.largo_maximo,
      solo_digitos: regla.solo_digitos,
      requiere_dv: regla.requiere_dv,
    })),
    modalidades_venta: Object.values(Modalidad),
    exclusiones_retracto: [...CATEGORIAS_SIN_RETRACTO].sort(),
    metodos_pago: Object.values(MetodoPago),
    nota_flete: FLETE_EXCLUIDO_DE_IVA,
    nota_impuestos_saludables: IMPUESTOS_SALUDABLES,
  };
}

/* --------------------------------------------------------------------- *
 *  1. buscar_productos
 * --------------------------------------------------------------------- */

/** Busca en el catálogo y valora cada referencia contra el destino. */
export function buscar_productos({
  consulta = "", categoria = null, destino = null, limite = _LIMITE_BUSQUEDA_POR_DEFECTO,
} = {}) {
  const ciudad = _ciudad(destino);
  let encontrados;
  if (categoria) {
    if (!Object.values(Categoria).includes(categoria)) {
      throw new Error(`${_repr(categoria)} is not a valid Categoria`);
    }
    encontrados = por_categoria(categoria);
  } else if (String(consulta).trim()) {
    encontrados = buscar(consulta);
  } else {
    encontrados = productos();
  }
  const tope = Math.max(1, Math.min(limite ?? _LIMITE_BUSQUEDA_POR_DEFECTO,
    _LIMITE_BUSQUEDA_MAXIMO));
  const nota = ciudad && ciudad.regimen_iva_especial
    ? `precios sin IVA por destino: ${ciudad.etiqueta} tiene regimen especial`
    : "precios de gondola con impuesto incluido, redondeados a la moneda de 50 pesos";
  return {
    consulta: categoria || consulta,
    destino: ciudad ? _ciudad_dto(ciudad) : null,
    total: encontrados.length,
    productos: encontrados.slice(0, tope).map((p) => _producto_dto(p, ciudad)),
    nota,
  };
}

/* --------------------------------------------------------------------- *
 *  2. cotizar_envio
 * --------------------------------------------------------------------- */

/** Cotiza el despacho y dice si ese destino admite contra entrega. */
export function cotizar_envio({
  destino, items = [], contraentrega = false, declarar_valor = true,
} = {}) {
  const ciudad = resolver_ciudad(destino);
  const carrito = _carrito(items);
  const [disponible, motivo] = diagnostico_contraentrega(ciudad);
  const tope = tope_contraentrega(ciudad);
  if (!carrito.tiene_despachables) {
    return {
      destino: _ciudad_dto(ciudad),
      despachable: false,
      peso_facturable_gramos: 0,
      valor_declarado: _monto(0),
      contraentrega_disponible: disponible,
      contraentrega_motivo: motivo,
      tope_contraentrega: _monto(tope),
      opciones: [],
      mejor: null,
      nota: "el pedido no tiene nada fisico que despachar: agrega una " +
        "referencia con bulto o entregalo en el mostrador",
    };
  }
  const liquidacion = liquidar(carrito.lineas_venta(), { destino: ciudad });
  const declarado = declarar_valor ? liquidacion.total_centavos : 0;
  const paquete = carrito.paquete({ valor_declarado_centavos: declarado });
  const opciones = cotizar(ciudad, paquete, {
    contraentrega,
    monto_a_recaudar_centavos: liquidacion.total_centavos,
  });
  return {
    destino: _ciudad_dto(ciudad),
    despachable: true,
    peso_facturable_gramos: paquete.peso_facturable_gramos,
    valor_declarado: _monto(declarado),
    contraentrega_disponible: disponible,
    contraentrega_motivo: motivo,
    tope_contraentrega: _monto(tope),
    opciones: opciones.map(_opcion_dto),
    mejor: opciones.length ? _opcion_dto(opciones[0]) : null,
    nota: FLETE_EXCLUIDO_DE_IVA,
  };
}

/* --------------------------------------------------------------------- *
 *  3. validar_documento_dian
 * --------------------------------------------------------------------- */

/** Valida la identificación del comprador contra las reglas del anexo DIAN. */
export function validar_documento_dian({ tipo, numero } = {}) {
  const dictado = separar_dv(numero ?? "")[1];
  let identidad;
  try {
    identidad = validar(tipo, numero);
  } catch (err) {
    if (!(err instanceof DominioError)) throw err;
    return {
      valido: false,
      tipo: String(tipo ?? "").trim().toUpperCase(),
      nombre_tipo: null,
      codigo_dian: null,
      numero: null,
      dv: null,
      dv_calculado: false,
      formateado: null,
      es_persona_juridica: false,
      mensaje: err.message,
    };
  }
  const calculado = identidad.regla.requiere_dv && dictado === null;
  let mensaje =
    `${identidad.regla.nombre}: identificacion valida; la DIAN la recibe con el codigo ` +
    `${identidad.codigo_dian} del anexo tecnico`;
  if (calculado) {
    mensaje += `. El digito de verificacion no venia dictado y se calculo: ${identidad.dv}`;
  }
  return {
    valido: true,
    tipo: identidad.tipo,
    nombre_tipo: identidad.regla.nombre,
    codigo_dian: identidad.codigo_dian,
    numero: identidad.numero,
    dv: identidad.dv,
    dv_calculado: calculado,
    formateado: identidad.formateado,
    es_persona_juridica: identidad.es_persona_juridica,
    mensaje,
  };
}

/* --------------------------------------------------------------------- *
 *  4. calcular_total_con_iva
 * --------------------------------------------------------------------- */

/** Liquida el carrito línea por línea con el régimen que le toca a cada una. */
export function calcular_total_con_iva({ items = [], destino = null, responsable_iva = true } = {}) {
  const ciudad = _ciudad(destino);
  const carrito = _carrito(items);
  const liquidacion = liquidar(carrito.lineas_venta(), { destino: ciudad, responsable_iva });
  return _liquidacion_dto(liquidacion, carrito, ciudad, responsable_iva);
}

/* --------------------------------------------------------------------- *
 *  5. consultar_derecho_retracto
 * --------------------------------------------------------------------- */

/** Calcula el plazo del Art. 47 contra el calendario colombiano real. */
export function consultar_derecho_retracto({
  fecha_entrega, modalidad = Modalidad.DOMICILIO, items = [], exclusiones = [], hoy = null,
} = {}) {
  const clave = String(modalidad).trim().toLowerCase();
  if (!Object.values(Modalidad).includes(clave)) {
    const admitidas = Object.values(Modalidad).join(", ");
    throw new Error(
      `modalidad de venta desconocida ${_repr(modalidad)}; admitidas: ${admitidas}`);
  }
  const entrega = desde_iso(fecha_entrega);
  const carrito = _carrito(items);
  const causales = new Set([...carrito.exclusiones_retracto, ...(exclusiones || [])]);
  const ventana = ventana_retracto(entrega, { modalidad: clave, exclusiones: causales });
  const calendario = ventana.vence ? dias_calendario(ventana.fecha_entrega, ventana.vence) : 0;
  const dia_hoy = hoy ? desde_iso(hoy) : null;
  return {
    aplica: ventana.aplica,
    motivo: ventana.motivo,
    modalidad: clave,
    fecha_entrega: a_iso(ventana.fecha_entrega),
    inicio: ventana.inicio ? a_iso(ventana.inicio) : null,
    vence: ventana.vence ? a_iso(ventana.vence) : null,
    dias_habiles: ventana.dias_habiles,
    dias_calendario: calendario,
    festivos_intermedios: ventana.festivos_intermedios.map((f) => ({
      fecha: a_iso(f.fecha),
      nombre: f.nombre,
      trasladado: f.trasladado,
      fecha_original: a_iso(f.fecha_original),
      fundamento: f.fundamento,
    })),
    exclusiones_detectadas: [...causales].sort(),
    dias_para_devolver_dinero: ventana.dias_para_devolver_dinero,
    vigente: dia_hoy ? ventana.vigente(dia_hoy) : null,
    dias_habiles_restantes: dia_hoy ? ventana.dias_habiles_restantes(dia_hoy) : null,
  };
}

/* --------------------------------------------------------------------- *
 *  6. metodos_de_pago
 * --------------------------------------------------------------------- */

/** Evalúa los cinco rieles contra el destino, el monto y el carrito. */
export function metodos_de_pago({
  items = [], destino, banco_pse = null, cliente_tiene_bancolombia = false, incluir_flete = true,
} = {}) {
  const ciudad = resolver_ciudad(destino);
  const carrito = _carrito(items);
  const liquidacion = liquidar(carrito.lineas_venta(), { destino: ciudad });
  let flete = 0;
  let recaudo = 0;
  if (incluir_flete && carrito.tiene_despachables) {
    const paquete = carrito.paquete({ valor_declarado_centavos: liquidacion.total_centavos });
    const terrestre = mejor_cotizacion(ciudad, paquete);
    flete = terrestre ? terrestre.total_centavos : 0;
    const con_recaudo = mejor_cotizacion(ciudad, paquete, {
      contraentrega: true,
      monto_a_recaudar_centavos: liquidacion.total_centavos + flete,
    });
    recaudo = con_recaudo ? con_recaudo.recaudo_centavos : 0;
  }
  const total = liquidacion.total_centavos + flete;
  const contexto_pago = ContextoPago({
    total_centavos: total,
    ciudad,
    base_sin_impuestos_centavos: liquidacion.base_gravable_centavos,
    comision_recaudo_centavos: recaudo,
    contiene_servicios: carrito.contiene_servicios,
    banco_pse,
    cliente_tiene_bancolombia,
  });
  const evaluaciones = evaluar(contexto_pago);
  const disponibles = evaluaciones.filter((e) => e.disponible);
  const parametros = contexto_pago.parametros;
  return {
    destino: _ciudad_dto(ciudad),
    desglose: {
      mercancia: _monto(liquidacion.total_centavos),
      flete: _monto(flete),
      total_pedido: _monto(total),
      nota_flete: FLETE_EXCLUIDO_DE_IVA,
    },
    metodos: evaluaciones.map(_metodo_dto),
    recomendado: disponibles.length ? disponibles[0].metodo : null,
    parametros: {
      anio: parametros.anio,
      uvt: _monto(parametros.uvt_centavos),
      smmlv: _monto(parametros.smmlv_centavos),
      tope_deposito_bajo_monto: _monto(parametros.tope_deposito_bajo_monto_centavos),
      exencion_gmf_mensual: _monto(parametros.exencion_gmf_mensual_centavos),
    },
    bancos_pse: [...BANCOS_PSE].sort(),
  };
}

/* ===================================================================== *
 *  Espejos con nombre de módulo, para que la página lea como el Python:
 *      dominio.documento.calcular_dv_nit("890903938")
 *      dominio.envio.diagnostico_contraentrega("Leticia")
 * ===================================================================== */

export const dinero = Object.freeze({
  CENTAVOS_POR_PESO, MULTIPLO_EFECTIVO, tarifa, aplicar_tarifa, redondear_a_pesos,
  redondear_efectivo, a_pesos, de_pesos, formatear_cop, porcentaje, reparto_proporcional,
});

export const documento = Object.freeze({
  DV_NIT_PESOS, REGLAS, Documento, TipoDocumento, calcular_dv_nit, es_valido,
  formatear_nit, normalizar, separar_dv, validar, verificar_dv_nit,
});

export const envio = Object.freeze({
  CIUDADES, FACTOR_VOLUMETRICO_CM3_POR_KG, FLETE_EXCLUIDO_DE_IVA,
  PESO_FACTURABLE_MINIMO_GRAMOS, REGIMEN_IVA_ESPECIAL, SIN_CONTRAENTREGA, TRANSPORTADORAS,
  Paquete, Zona, buscar_ciudades, cotizar, cubre, diagnostico_contraentrega,
  mejor_cotizacion, resolver_ciudad, tope_contraentrega,
});

export const impuesto = Object.freeze({
  IMPUESTOS_SALUDABLES, TARIFA_INC_RESTAURANTES, TARIFA_IVA_GENERAL, TARIFA_IVA_REDUCIDA,
  TRATAMIENTOS, LineaVenta, Regimen, liquidar, liquidar_linea, resumen_descontables,
});

export const retracto = Object.freeze({
  CATEGORIAS_SIN_RETRACTO, DIAS_HABILES_RETRACTO, DIAS_PARA_DEVOLVER_DINERO, Modalidad,
  aplica_retracto, dias_habiles_entre, es_dia_habil, es_festivo, festivos, pascua,
  sumar_dias_habiles, ventana_retracto, fecha, desde_iso, a_iso, sumar_dias, dias_calendario,
});

export const pago = Object.freeze({
  BANCOS_PSE, PARAMETROS_VIGENTES, SMMLV_TOPE_DEPOSITO_BAJO_MONTO, TARIFA_GMF,
  TARIFA_RETEFUENTE_TARJETAS, UVT_EXENTAS_GMF_MENSUALES, ContextoPago, MetodoPago,
  ParametrosFiscales, evaluar, gmf, recomendar,
});

export const catalogo = Object.freeze({
  CATALOGO, COMERCIO, Carrito, Categoria, armar_carrito, buscar, linea_venta, obtener,
  por_categoria, precio_al_publico, productos,
});

/** Las seis herramientas WebMCP, indexadas por su nombre de herramienta. */
export const herramientas = Object.freeze({
  buscar_productos,
  cotizar_envio,
  validar_documento_dian,
  calcular_total_con_iva,
  consultar_derecho_retracto,
  metodos_de_pago,
});
