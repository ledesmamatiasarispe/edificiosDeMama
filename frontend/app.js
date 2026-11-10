'use strict';
// Pantalla única: cada vista pide sus datos a la API y se dibuja en #vista. Sin lógica de negocio acá:
// lo que se valida y se calcula lo hace el servidor, y sus mensajes se muestran tal cual.

const S = { token: null, usuario: null, consorcios: [], consorcio: null };

// ── utilidades ──
const $ = (sel, raiz = document) => raiz.querySelector(sel);
const esc = v => String(v ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
const hoyISO = () => { const d = new Date(); d.setMinutes(d.getMinutes() - d.getTimezoneOffset()); return d.toISOString().slice(0, 10); };
const fecha = iso => iso ? iso.slice(0, 10).split('-').reverse().join('/') : '';
const plata = c => c == null ? '' : '$ ' + (c / 100).toLocaleString('es-AR', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
const plataInput = c => c == null ? '' : (c / 100).toLocaleString('es-AR', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
const leer = k => { try { return localStorage.getItem(k); } catch { return null; } };
const guardar = (k, v) => { try { v == null ? localStorage.removeItem(k) : localStorage.setItem(k, v); } catch { /* sin almacenamiento */ } };
const TIPOS = { vivienda: 'Vivienda', local: 'Local', cochera: 'Cochera', baulera: 'Baulera', otro: 'Otro' };
const MODALIDADES = ['efectivo', 'transferencia', 'depósito', 'cheque', 'otro'];

async function api(ruta, { metodo = 'GET', datos } = {}) {
  const opts = { method: metodo, headers: {} };
  if (S.token) opts.headers.Authorization = 'Bearer ' + S.token;
  if (datos !== undefined) { opts.headers['Content-Type'] = 'application/json'; opts.body = JSON.stringify(datos); }
  const r = await fetch(ruta, opts);
  if (r.status === 401 && !ruta.endsWith('/login')) { salir(); throw new Error('La sesión venció: iniciar sesión de nuevo.'); }
  const cuerpo = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(typeof cuerpo.detail === 'string' ? cuerpo.detail : 'No se pudo completar la operación.');
  return cuerpo;
}

let _avisoTimer;
function avisar(texto, mal = false) {
  const a = $('#aviso');
  a.textContent = texto; a.classList.toggle('mal', mal); a.classList.remove('oculto');
  clearTimeout(_avisoTimer); _avisoTimer = setTimeout(() => a.classList.add('oculto'), mal ? 7000 : 3500);
}

function abrirModal(html, grande = false) {
  $('#modal-cuerpo').innerHTML = html; $('#modal').classList.toggle('grande', grande); $('#modal').showModal();
  const primero = $('#modal-cuerpo input:not([type=hidden]), #modal-cuerpo select, #modal-cuerpo textarea');
  if (primero) primero.focus();
}
function cerrarModal() { $('#modal').close(); }

/** Lee un formulario a un objeto: los checkbox dan true/false, el resto texto crudo (lo valida el servidor). */
function leerForm(form) {
  const d = {};
  for (const el of form.elements) {
    if (!el.name) continue;
    d[el.name] = el.type === 'checkbox' ? el.checked : el.value;
  }
  return d;
}

/** Arma un formulario en el modal y al enviarlo llama a 'accion'. Un error del servidor se muestra en el formulario. */
function formModal(titulo, campos, accion, { boton = 'Guardar', grande = false, intro = '' } = {}) {
  abrirModal(`<h2>${titulo}</h2>${intro}<form id="f-modal"><div class="campos">${campos}</div>
    <p class="error" role="alert"></p>
    <div class="botones"><button class="primario" type="submit">${boton}</button><button type="button" onclick="cerrarModal()">Cancelar</button></div></form>`, grande);
  const f = $('#f-modal');
  f.addEventListener('submit', async ev => {
    ev.preventDefault();
    const err = $('.error', f), b = $('button[type=submit]', f);
    err.textContent = ''; b.disabled = true;
    try { await accion(leerForm(f)); }
    catch (e) { err.textContent = e.message; }
    finally { b.disabled = false; }
  });
  return f;
}

const opciones = (lista, valor, vacio = null) =>
  (vacio !== null ? `<option value="">${esc(vacio)}</option>` : '') +
  lista.map(([v, t]) => `<option value="${esc(v)}" ${String(v) === String(valor ?? '') ? 'selected' : ''}>${esc(t)}</option>`).join('');
const campo = (etiqueta, nombre, valor = '', extra = '') => `<label>${etiqueta} <input name="${nombre}" value="${esc(valor)}" ${extra}></label>`;

async function hacer(promesa, mensaje, destino) {
  try { await promesa; if (mensaje) avisar(mensaje); if (destino) irA(destino); }
  catch (e) { avisar(e.message, true); }
}

/** Abre una ventana con solo ese contenido y el diálogo de impresión (para guardar como PDF o imprimir). */
function imprimir(titulo, html) {
  const w = window.open('', '_blank');
  if (!w) return avisar('El navegador bloqueó la ventana de impresión: permitir ventanas emergentes para este sitio.', true);
  w.document.write(`<!doctype html><html lang="es"><head><meta charset="utf-8"><title>${esc(titulo)}</title>
    <link rel="stylesheet" href="/static/styles.css"></head><body class="hoja">${html}
    <script>window.onload = () => { window.print(); }<\/script></body></html>`);
  w.document.close();
}

// ── consorcio elegido (lo comparten Expensas, Cobros y Saldos) ──
async function cargarConsorcios() {
  S.consorcios = (await api('/api/consorcios')).filter(c => c.activo);
  const guardado = Number(leer('edif_consorcio'));
  S.consorcio = S.consorcios.find(c => c.id === guardado)?.id || S.consorcios[0]?.id || null;
}
function elegirConsorcio(vista) {
  if (!S.consorcios.length) return '<p>Todavía no hay consorcios. Crear uno en <a href="#consorcios">Consorcios</a>.</p>';
  return `<label class="elegir-consorcio">Consorcio
    <select onchange="S.consorcio = Number(this.value); guardar('edif_consorcio', this.value); irA('${vista}')">
      ${opciones(S.consorcios.map(c => [c.id, c.nombre]), S.consorcio)}</select></label>`;
}

// ── sesión ──
async function entrar() {
  try { S.usuario = await api('/api/auth/yo'); } catch { return mostrarLogin(); }
  $('#login').classList.add('oculto'); $('#app').classList.remove('oculto');
  $('#usuario-nombre').textContent = S.usuario.nombre;
  document.querySelectorAll('.solo-admin').forEach(el => el.classList.toggle('oculto', !S.usuario.es_admin));
  if (S.usuario.debe_cambiar) { $('#vista').innerHTML = ''; return modalPassword(true); }
  try { await cargarConsorcios(); } catch (e) { return avisar(e.message, true); }
  irA(location.hash.slice(1) || 'inicio');
  if (S.usuario.es_admin) preguntarActualizacion();
}

// ── actualizaciones ──
/** Al entrar un administrador: si hay una versión nueva (y no se pospuso), se pregunta si se instala. */
async function preguntarActualizacion() {
  let a;
  try { a = await api('/api/actualizacion'); } catch { return; }   // sin respuesta, se pregunta la próxima vez
  if (!a.preguntar || $('#modal').open) return;
  abrirModal(`<h2 tabindex="-1">Hay una versión nueva</h2>
    <p>Está disponible la versión <b>${esc(a.nueva)}</b> (la instalada es la ${esc(a.version)}). ¿Querés actualizar ahora?</p>
    ${a.notas ? `<div class="notas-version">${esc(a.notas)}</div>` : ''}
    <p class="sutil">Antes se hace una copia de la base. La app se reinicia sola en menos de un minuto: avisá a quien la esté usando. Los datos no se tocan.</p>
    <p class="error" role="alert"></p>
    <div class="botones"><button class="primario" id="act-si" ${a.instalable ? '' : 'disabled'}>Actualizar ahora</button>
      <button id="act-no">Ahora no (preguntar en una semana)</button></div>
    ${a.instalable ? '' : '<p class="sutil">Esta versión no trae el paquete para instalarse sola: hay que actualizar a mano.</p>'}`);
  $('#modal-cuerpo h2').focus();
  $('#act-no').addEventListener('click', async () => {
    try { const r = await api('/api/actualizacion/posponer', { metodo: 'POST' }); cerrarModal(); avisar(`No se vuelve a preguntar hasta el ${fecha(r.pospuesta_hasta)}. Se puede actualizar antes desde Administración.`); }
    catch (e) { $('#modal .error').textContent = e.message; }
  });
  $('#act-si').addEventListener('click', () => instalarActualizacion());
}

/** Instala y espera a que la app vuelva con la versión nueva; entonces recarga la página. */
async function instalarActualizacion() {
  const antes = (await api('/api/version').catch(() => ({}))).version;
  abrirModal(`<h2 tabindex="-1">Actualizando…</h2><p role="status">Bajando la versión nueva y guardando una copia de la base. Después la app se reinicia sola: esta página se recarga cuando esté lista.</p>
    <p class="error" role="alert"></p>`);
  $('#modal-cuerpo h2').focus();
  try { await api('/api/actualizacion/instalar', { metodo: 'POST' }); }
  catch (e) { $('#modal .error').textContent = e.message; $('#modal-cuerpo').insertAdjacentHTML('beforeend', '<div class="botones"><button onclick="cerrarModal()">Cerrar</button></div>'); return; }
  const inicio = Date.now();
  const esperar = async () => {
    try {
      const r = await fetch('/api/version');
      if (r.ok && (await r.json()).version !== antes) return location.reload();
    } catch { /* todavía reiniciando */ }
    if (Date.now() - inicio > 5 * 60 * 1000) {
      $('#modal .error').textContent = 'La app tarda en volver. Si no abre, iniciala de nuevo.';
      return;
    }
    setTimeout(esperar, 2000);
  };
  setTimeout(esperar, 3000);
}

async function buscarActualizacion(boton) {
  boton.disabled = true; boton.textContent = 'Buscando…';
  try { await api('/api/actualizacion/buscar', { metodo: 'POST' }); irA('administracion'); }
  catch (e) { avisar(e.message, true); boton.disabled = false; boton.textContent = 'Buscar ahora'; }
}

function htmlVersion(a) {
  const admin = S.usuario.es_admin;
  let estado;
  if (!a.repo) estado = '<p class="sutil">No hay un repositorio de actualizaciones configurado.</p>';
  else if (a.error) estado = `<p class="error">${esc(a.error)}</p>`;
  else if (a.disponible) estado = `<p>Hay una versión nueva: <b>${esc(a.nueva)}</b>${a.url_release ? ` · <a href="${esc(a.url_release)}" target="_blank" rel="noopener">ver en GitHub</a>` : ''}</p>
    ${a.notas ? `<div class="notas-version">${esc(a.notas)}</div>` : ''}
    ${a.pospuesta_hasta ? `<p class="sutil">Se pospuso: al entrar no se vuelve a preguntar hasta el ${fecha(a.pospuesta_hasta)}.</p>` : ''}
    ${admin ? (a.instalable ? '<button class="primario" onclick="instalarActualizacion()">Actualizar ahora</button>'
      : '<p class="sutil">Esta versión no trae el paquete para instalarse sola: hay que actualizar a mano.</p>') : '<p class="sutil">La instala un administrador.</p>'}`;
  else estado = '<p>Estás usando la última versión.</p>';
  return `<section class="tarjeta"><h3>Versión y actualizaciones</h3>
    <p>Versión instalada: <b>${esc(a.version)}</b></p>${estado}
    ${a.repo ? `<p class="sutil">Se busca en GitHub (${esc(a.repo)}) cada vez que arranca la app${a.buscado_en ? ' · última búsqueda: ' + esc(a.buscado_en) : ''}.</p>` : ''}
    ${admin && a.repo ? '<button onclick="buscarActualizacion(this)">Buscar ahora</button>' : ''}</section>`;
}

function modalPassword(obligatorio = false) {
  abrirModal(`
    <h2>${obligatorio ? 'Elegí tu contraseña' : 'Cambiar contraseña'}</h2>
    ${obligatorio ? '<p>Estás entrando con una contraseña provisoria. Antes de seguir, elegí una propia.</p>' : ''}
    <form id="f-password"><div class="campos">
      <label class="ancho">Contraseña ${obligatorio ? 'provisoria' : 'actual'} <input type="password" name="actual" autocomplete="current-password" required></label>
      <label>Nueva (mínimo 6) <input type="password" name="nueva" autocomplete="new-password" required></label>
      <label>Repetir la nueva <input type="password" name="repetida" autocomplete="new-password" required></label>
    </div><p class="error" role="alert"></p>
    <div class="botones"><button class="primario" type="submit">Guardar</button>
      ${obligatorio ? '<button type="button" onclick="cerrarModal(); salir()">Salir</button>' : '<button type="button" onclick="cerrarModal()">Cancelar</button>'}</div></form>`);
  $('#modal').dataset.obligatorio = obligatorio ? '1' : '';
  const f = $('#f-password');
  f.addEventListener('submit', async ev => {
    ev.preventDefault();
    const d = leerForm(f);
    try {
      if (d.nueva !== d.repetida) throw new Error('Las dos contraseñas nuevas no coinciden.');
      await api('/api/auth/password', { metodo: 'POST', datos: d });
      $('#modal').dataset.obligatorio = ''; cerrarModal(); avisar('Contraseña cambiada.');
      if (obligatorio) entrar();
    } catch (e) { $('.error', f).textContent = e.message; }
  });
}
$('#modal').addEventListener('cancel', ev => { if ($('#modal').dataset.obligatorio) ev.preventDefault(); });
$('#mi-password').addEventListener('click', () => modalPassword(false));

function mostrarLogin() { $('#app').classList.add('oculto'); $('#login').classList.remove('oculto'); $('input[name=usuario]').focus(); }

function salir() {
  if (S.token) fetch('/api/auth/logout', { method: 'POST', headers: { Authorization: 'Bearer ' + S.token } }).catch(() => {});
  S.token = null; guardar('edif_token', null); mostrarLogin();
}

$('#form-login').addEventListener('submit', async ev => {
  ev.preventDefault();
  $('#login-error').textContent = '';
  try {
    const r = await api('/api/auth/login', { metodo: 'POST', datos: leerForm(ev.target) });
    S.token = r.token; guardar('edif_token', r.token); ev.target.reset(); entrar();
  } catch (e) { $('#login-error').textContent = e.message; }
});
$('#salir').addEventListener('click', salir);

// ── navegación ──
const VISTAS = {};
const PESTANA = { consorcio: 'consorcios', liquidacion: 'expensas', cuenta: 'saldos' };
function irA(nombre) {
  const [vista, param] = nombre.split('/');
  if (!VISTAS[vista]) return irA('inicio');
  if (location.hash.slice(1) !== nombre) history.replaceState(null, '', '#' + nombre);
  const pestana = PESTANA[vista] || vista;
  document.querySelectorAll('#menu a').forEach(a => {
    a.classList.toggle('activo', a.dataset.vista === pestana);
    a.toggleAttribute('aria-current', a.dataset.vista === pestana);
  });
  $('#vista').innerHTML = '<p class="sutil">Cargando…</p>';
  VISTAS[vista](param).then(() => $('#vista').focus({ preventScroll: true }))
    .catch(e => { $('#vista').innerHTML = `<p class="error">${esc(e.message)}</p>`; });
}
$('#menu').addEventListener('click', ev => { if (ev.target.dataset.vista) { ev.preventDefault(); irA(ev.target.dataset.vista); } });
window.addEventListener('hashchange', () => S.usuario && irA(location.hash.slice(1)));

// ── INICIO ──
VISTAS.inicio = async () => {
  const cons = await api('/api/resumen');
  $('#vista').innerHTML = `
    <div class="encabezado"><h2>Inicio</h2></div>
    ${cons.length ? '' : '<p>Todavía no hay consorcios. Empezar en <a href="#consorcios">Consorcios</a>.</p>'}
    <div class="grilla">${cons.map(c => `
      <section class="tarjeta" aria-label="${esc(c.nombre)}">
        <h3>${esc(c.nombre)}</h3><p class="sutil">${esc(c.direccion)} · ${c.unidades} unidades</p>
        <dl class="datos">
          <dt>Última liquidación</dt><dd>${c.ultima ? `${esc(c.ultima.nombre)} (${c.ultima.estado})` : 'ninguna'}</dd>
          <dt>Deuda total de las unidades</dt><dd>${plata(c.deuda_total)}</dd>
          <dt>Unidades con deuda vencida</dt><dd>${c.morosos ? `<span class="chip rojo">${c.morosos}</span>` : '<span class="chip verde">ninguna</span>'}</dd>
          <dt>Cobrado hoy</dt><dd>${plata(c.cobrado_hoy)}</dd>
        </dl>
        <div class="botones">
          <button class="primario" onclick="verFicha(${c.id}, ${c.unidades})">Ver ficha</button>
          <button onclick="S.consorcio=${c.id}; irA(${c.ultima ? `'liquidacion/${c.ultima.id}'` : "'expensas'"})">Ver expensas</button>
          <button onclick="S.consorcio=${c.id}; irA('cobros')">Cobrar</button>
          <button onclick="S.consorcio=${c.id}; irA('saldos')">Saldos</button>
        </div>
      </section>`).join('')}</div>`;
};

// ── CONSORCIOS ──
VISTAS.consorcios = async () => {
  const lista = await api('/api/consorcios');
  $('#vista').innerHTML = `
    <div class="encabezado"><h2>Consorcios</h2><div class="botones"><button class="primario" onclick="modalConsorcio()">Nuevo consorcio</button></div></div>
    <div class="tarjeta tabla-wrap"><table><caption class="sr">Consorcios</caption>
      <thead><tr><th>Nombre</th><th>Dirección</th><th>Unidades</th><th>Interés por mora</th><th>Estado</th><th></th></tr></thead><tbody>
      ${lista.map(c => `<tr class="${c.activo ? '' : 'baja'}"><td><a href="#consorcio/${c.id}">${esc(c.nombre)}</a></td><td>${esc(c.direccion)}</td>
        <td>${c.unidades}</td><td>${c.interes_mora}% mensual</td><td>${c.activo ? 'Activo' : 'De baja'}</td>
        <td class="botones"><button class="chico" onclick="irA('consorcio/${c.id}')">Abrir</button>
          <button class="chico ${c.activo ? 'peligro' : ''}" onclick="hacer(api('/api/consorcios/${c.id}/${c.activo ? 'baja' : 'alta'}', {metodo:'POST'}).then(cargarConsorcios), '${c.activo ? 'Consorcio dado de baja.' : 'Consorcio reactivado.'}', 'consorcios')">${c.activo ? 'Dar de baja' : 'Reactivar'}</button></td></tr>`).join('')}
    </tbody></table></div>`;
};

const SI_NO = [['1', 'Sí'], ['0', 'No']];
const siNo = (etiqueta, nombre, valor, ayuda = '') =>
  `<label>${etiqueta}${ayuda ? ` <small class="sutil">${ayuda}</small>` : ''} <select name="${nombre}">${opciones(SI_NO, valor ? '1' : '0')}</select></label>`;

function camposConsorcio(c = {}) {
  const nuevo = c.id == null;
  return `<fieldset class="ancho"><legend>Datos del edificio</legend><div class="campos">` +
    campo('Nombre (obligatorio)', 'nombre', c.nombre, 'required') + campo('Dirección (obligatorio)', 'direccion', c.direccion, 'required') +
    campo('Localidad', 'localidad', c.localidad) + campo('Código postal', 'cp', c.cp) + campo('CUIT', 'cuit', c.cuit) +
    campo('Email para enviar y recibir respuestas de las expensas (obligatorio)', 'email', c.email, 'type="email" required') +
    campo('Clave SUTERH', 'clave_suterh', c.clave_suterh) +
    `<label>Categoría del edificio <select name="categoria">${opciones([['1', 'Categoría 1'], ['2', 'Categoría 2'], ['3', 'Categoría 3'], ['4', 'Categoría 4']], c.categoria, '— sin categoría —')}</select></label>` +
    campo('Año de construcción', 'anio_construccion', c.anio_construccion ?? '', 'inputmode="numeric"') +
    `</div></fieldset><fieldset class="ancho"><legend>Cómo se liquidan las expensas</legend><div class="campos">` +
    `<label>Configuración de superficies (obligatorio) <select name="superficies">${opciones([['porcentual', 'Porcentual (cada unidad tiene su %)'], ['absoluta', 'Absoluta (cada unidad tiene sus m²)']], c.superficies || 'porcentual')}</select></label>` +
    campo('Interés por mora (% mensual, obligatorio)', 'interes_mora', c.interes_mora ?? 0, 'inputmode="decimal" required') +
    `<label>Tipo de interés (obligatorio) <select name="tipo_interes">${opciones([['simple', 'Simple (no cobra interés sobre interés)'], ['compuesto', 'Compuesto (cobra interés sobre interés)']], c.tipo_interes || 'simple')}</select></label>` +
    campo('Día de vencimiento de las expensas (1 a 28)', 'dia_vencimiento', c.dia_vencimiento ?? 10, 'inputmode="numeric"') +
    siNo('Mostrar inquilino en el reparto', 'mostrar_inquilino', c.mostrar_inquilino) +
    siNo('Envía comprobantes de gastos', 'envia_comprobantes', c.envia_comprobantes, '(para cuando haya envío por email)') +
    siNo('El pago cancela primero la deuda más vieja (obligatorio)', 'imputa_a_deuda', nuevo ? true : c.imputa_a_deuda) +
    siNo('Liquida mes vencido (obligatorio)', 'liquida_mes_vencido', nuevo ? true : c.liquida_mes_vencido, '(los gastos del mes que ya pasó)') +
    `<label class="ancho">Nota que sale en las expensas <textarea name="nota_expensas">${esc(c.nota_expensas || '')}</textarea></label>` +
    `</div></fieldset><fieldset class="ancho"><legend>Caja y formas de pago (salen al pie de las expensas)</legend><div class="campos">` +
    campo('Caja inicial en pesos (lo que había al empezar a usar la app; puede ser negativo)', 'caja_inicial', plataInput(c.caja_inicial ?? 0), 'inputmode="decimal"') +
    campo('Titular de la cuenta', 'banco_titular', c.banco_titular) + campo('Banco', 'banco_nombre', c.banco_nombre) +
    campo('Sucursal', 'banco_sucursal', c.banco_sucursal) + campo('Número de cuenta', 'banco_cuenta', c.banco_cuenta) +
    campo('CBU o CVU', 'banco_cbu', c.banco_cbu, 'inputmode="numeric"') + campo('Alias', 'banco_alias', c.banco_alias) +
    campo('Código de pago electrónico', 'codigo_pago', c.codigo_pago) +
    `</div></fieldset>`;
}
const LINK_ANATOCISMO = '<button type="button" class="link azul" onclick="explicarAnatocismo()" aria-haspopup="dialog">anatocismo</button>';
const AVISO_INTERES = `<p class="aviso-fijo">Atención: verificar el tipo de interés por mora que fija el reglamento o la asamblea. El interés compuesto cobra interés sobre interés (${LINK_ANATOCISMO}).</p>`;

/** Explicación en una ventana aparte, encima de la ficha o del formulario (no los cierra). */
function explicarAnatocismo() {
  $('#ayuda-cuerpo').innerHTML = `
    <h2 id="ayuda-titulo" tabindex="-1">¿Qué es el anatocismo?</h2>
    <p><b>Anatocismo</b> es cobrar <b>intereses sobre intereses</b>. Pasa cuando los intereses por mora que no se pagaron
      se suman a la deuda, y el mes siguiente se calcula el interés también sobre ellos. Así la deuda crece cada vez más rápido.</p>
    <h3>Un ejemplo</h3>
    <p>Una unidad debe $100.000 de expensas vencidas, con un interés del 3% por mes, y no paga nada:</p>
    <ul>
      <li><b>Interés simple:</b> el 3% se calcula siempre sobre los $100.000. Son $3.000 por mes: en 6 meses, $18.000 de interés.</li>
      <li><b>Interés compuesto (anatocismo):</b> el segundo mes el 3% se calcula sobre $103.000, el tercero sobre $106.090, y así.
        En 6 meses son unos $19.400 de interés. La diferencia crece cuanto más tiempo pasa.</li>
    </ul>
    <h3>¿Por qué la app avisa?</h3>
    <p>En Argentina el anatocismo está <b>prohibido como regla general</b> (artículo 770 del Código Civil y Comercial).
      Solo se permite en casos puntuales, por ejemplo si hay un acuerdo escrito expreso que lo autorice, o cuando lo dispone un juez.</p>
    <p>Por eso, antes de elegir "Compuesto", hay que revisar qué dice el <b>reglamento de copropiedad</b> o lo que resolvió la
      <b>asamblea</b>. Si no lo dicen claramente, lo seguro es usar <b>interés simple</b>, que es lo que la app propone de entrada.</p>
    <p class="sutil">Esto es una explicación general, no un consejo legal. Ante una duda concreta, consultar con un abogado.</p>
    <div class="botones"><button class="primario" type="button" onclick="$('#ayuda').close()">Entendido</button></div>`;
  $('#ayuda').showModal();
  $('#ayuda-cuerpo h2').focus();
}

function modalConsorcio() {
  formModal('Nuevo consorcio', camposConsorcio(), async d => {
    const c = await api('/api/consorcios', { metodo: 'POST', datos: d });
    await cargarConsorcios(); cerrarModal(); avisar('Consorcio creado. Ahora cargá sus unidades.'); irA('consorcio/' + c.id);
  }, { grande: true, intro: AVISO_INTERES });
}

VISTAS.consorcio = async id => {
  const [c, u, fijos, provs, rubros, encargados, juicios] = await Promise.all([api('/api/consorcios/' + id), api(`/api/consorcios/${id}/unidades`),
    api(`/api/consorcios/${id}/gastos-fijos`), api('/api/proveedores'), api('/api/rubros'), api(`/api/consorcios/${id}/encargados`),
    api(`/api/consorcios/${id}/juicios`)]);
  S.c = c; S.unidades = u.unidades; S.fijos = fijos; S.provs = provs; S.rubros = rubros; S.encargados = encargados; S.juicios = juicios;
  const letras = c.grupos.map(g => g.letra);
  const m2 = c.superficies === 'absoluta', unidad = m2 ? ' m²' : '%';
  const control = letras.map(l => {
    const suma = u.control[l] || 0, ok = m2 ? suma > 0 : Math.abs(suma - 100) < 0.01;
    return `<span class="chip ${ok ? 'verde' : 'rojo'}">Grupo ${l}: ${suma.toLocaleString('es-AR')}${unidad}${ok ? '' : (m2 ? ' (falta cargar superficies)' : ' (tiene que sumar 100%)')}</span>`;
  }).join(' ');
  S.cantUnidades = u.unidades.length;
  $('#vista').innerHTML = `
    <div class="encabezado"><h2>${esc(c.nombre)}</h2><div class="botones">
      <button onclick="modalEditarConsorcio('consorcio/${c.id}')">Editar datos</button><button onclick="modalGrupos()">Grupos de gastos</button></div></div>
    <section class="tarjeta"><h3>Datos del consorcio</h3>${fichaConsorcio(c, true)}</section>

    <section class="tarjeta"><div class="encabezado"><h3>Unidades (${u.unidades.filter(x => x.activa).length})</h3>
      <div class="botones"><button class="primario" onclick="modalUnidad()">Nueva unidad</button></div></div>
      <p>${control}</p>
      <div class="tabla-wrap"><table><caption class="sr">Unidades del consorcio</caption>
      <thead><tr><th>Unidad</th><th>Piso y depto</th><th>Tipo</th>${letras.map(l => `<th class="num">${m2 ? 'm²' : '%'} ${l}</th>`).join('')}<th>Propietarios e inquilinos</th><th></th></tr></thead><tbody>
      ${u.unidades.map(x => `<tr class="${x.activa ? '' : 'baja'}"><td><b>${esc(x.nombre)}</b></td><td>${esc([x.piso, x.depto].filter(Boolean).join(' '))}</td>
        <td>${TIPOS[x.tipo]}</td>${letras.map(l => `<td>${x.porcentajes[l] != null ? x.porcentajes[l].toLocaleString('es-AR') : '—'}</td>`).join('')}
        <td>${x.personas.map(p => `${esc(p.apellido)}, ${esc(p.nombre)} <span class="sutil">(${p.rol})</span>`).join('<br>') || '<span class="sutil">sin cargar</span>'}</td>
        <td class="botones"><button class="chico" onclick="modalUnidad(${x.id})">Editar</button>
          <button class="chico" onclick="modalPersonasUnidad(${x.id})">Personas</button>
          <button class="chico" onclick="irA('cuenta/${x.id}')">Cuenta corriente</button>
          <button class="chico ${x.activa ? 'peligro' : ''}" onclick="hacer(api('/api/unidades/${x.id}/${x.activa ? 'baja' : 'alta'}', {metodo:'POST'}), null, 'consorcio/${id}')">${x.activa ? 'Dar de baja' : 'Reactivar'}</button></td></tr>`).join('')}
      </tbody></table></div></section>

    <section class="tarjeta"><div class="encabezado"><h3>Gastos fijos de todos los meses</h3>
      <div class="botones"><button class="primario" onclick="modalGastoFijo()">Nuevo gasto fijo</button></div></div>
      <p class="sutil">Se copian solos a cada liquidación nueva (después se pueden cambiar en esa liquidación).</p>
      <div class="tabla-wrap"><table><caption class="sr">Gastos fijos</caption><thead><tr><th>Rubro</th><th>Grupo</th><th>Descripción</th><th>Proveedor</th><th class="num">Importe</th><th></th></tr></thead><tbody>
      ${fijos.map(g => `<tr class="${g.activo ? '' : 'baja'}"><td>${g.rubro ? g.rubro_numero + '. ' + esc(g.rubro) : '<span class="sutil">sin rubro</span>'}</td><td>${g.letra}</td><td>${esc(g.descripcion)}</td><td>${esc(g.proveedor || '')}</td><td class="num">${plata(g.importe)}</td>
        <td class="botones"><button class="chico" onclick="modalGastoFijo(${g.id})">Editar</button>
        <button class="chico ${g.activo ? 'peligro' : ''}" onclick="hacer(api('/api/gastos-fijos/${g.id}/${g.activo ? 'baja' : 'alta'}', {metodo:'POST'}), null, 'consorcio/${id}')">${g.activo ? 'Quitar' : 'Volver a usar'}</button></td></tr>`).join('') || '<tr><td colspan="6" class="sutil">No hay gastos fijos.</td></tr>'}
      </tbody></table></div></section>

    <section class="tarjeta"><div class="encabezado"><h3>Personal (encargados)</h3>
      <div class="botones"><button class="primario" onclick="modalEncargado()">Nuevo encargado</button></div></div>
      <p class="sutil">Los conceptos de sueldo de cada encargado se copian solos a cada liquidación nueva (rubro 1, remuneraciones al personal).
        Costo para el consorcio = remuneraciones − descuentos + aportes y contribuciones.</p>
      ${encargados.map(e => `<div class="bloque ${e.activo ? '' : 'baja'}"><div class="encabezado"><h4>${esc(e.apellido)}, ${esc(e.nombre)}
          <span class="sutil">· ${esc(e.cargo || 'sin cargo')} · grupo ${e.letra}${e.activo ? '' : ' · DE BAJA'}</span></h4>
        <div class="botones"><button class="chico" onclick="modalEncargado(${e.id})">Editar</button>
          <button class="chico" onclick="modalSueldoFijo(${e.id})">Agregar concepto</button>
          <button class="chico ${e.activo ? 'peligro' : ''}" onclick="hacer(api('/api/encargados/${e.id}/${e.activo ? 'baja' : 'alta'}', {metodo:'POST'}), null, 'consorcio/${id}')">${e.activo ? 'Dar de baja' : 'Reactivar'}</button></div></div>
        <div class="tabla-wrap"><table><caption class="sr">Conceptos de sueldo de ${esc(e.apellido)}</caption><thead><tr><th>Tipo</th><th>Concepto</th><th class="num">Importe</th><th></th></tr></thead><tbody>
        ${e.fijos.map(f => `<tr class="${f.activo ? '' : 'baja'}"><td>${TIPOS_SUELDO[f.tipo]}</td><td>${esc(f.concepto)}</td><td class="num">${plata(f.importe)}</td>
          <td class="botones"><button class="chico" onclick="modalSueldoFijo(${e.id}, ${f.id})">Editar</button>
          <button class="chico ${f.activo ? 'peligro' : ''}" onclick="hacer(api('/api/sueldos-fijos/${f.id}/${f.activo ? 'baja' : 'alta'}', {metodo:'POST'}), null, 'consorcio/${id}')">${f.activo ? 'Quitar' : 'Volver a usar'}</button></td></tr>`).join('') || '<tr><td colspan="4" class="sutil">Sin conceptos.</td></tr>'}
        </tbody></table></div></div>`).join('') || '<p class="sutil">No hay personal cargado.</p>'}
    </section>

    <section class="tarjeta"><div class="encabezado"><h3>Juicios</h3>
      <div class="botones"><button class="primario" onclick="modalJuicio()">Nuevo juicio</button></div></div>
      <div class="tabla-wrap"><table><caption class="sr">Juicios</caption><thead><tr><th>Juzgado</th><th>Expediente</th><th>Carátula</th><th class="num">Monto reclamado</th><th>Estado</th><th>Sale en expensas</th><th></th></tr></thead><tbody>
      ${juicios.map(j => `<tr><td>${esc(j.juzgado)}</td><td>${esc(j.expediente)}</td><td>${esc(j.caratula)}</td><td class="num">${j.monto_reclamado != null ? plata(j.monto_reclamado) : '—'}</td>
        <td>${esc(j.estado)}</td><td>${j.visible ? 'Sí' : 'No'}</td>
        <td class="botones"><button class="chico" onclick="modalJuicio(${j.id})">Editar</button>
        <button class="chico peligro" onclick="if(confirm('¿Borrar este juicio?')) hacer(api('/api/juicios/${j.id}', {metodo:'DELETE'}), 'Juicio borrado.', 'consorcio/${id}')">Borrar</button></td></tr>`).join('') || '<tr><td colspan="7" class="sutil">No hay juicios.</td></tr>'}
      </tbody></table></div></section>`;
};

const TIPOS_SUELDO = { remuneracion: 'Remuneración (suma)', descuento: 'Descuento (resta)', aporte: 'Aporte o contribución (suma)' };

function modalEncargado(id) {
  const e = id ? S.encargados.find(x => x.id === id) : { letra: 'A' };
  formModal(id ? 'Editar encargado' : 'Nuevo encargado',
    campo('Nombre', 'nombre', e.nombre, 'required') + campo('Apellido', 'apellido', e.apellido, 'required') + campo('DNI', 'dni', e.dni) +
    campo('CUIL', 'cuil', e.cuil) + campo('Teléfono', 'telefono', e.telefono, 'type="tel"') + campo('Cargo', 'cargo', e.cargo, 'placeholder="ej. Encargado permanente"') +
    campo('Categoría del encargado', 'categoria', e.categoria) + campo('Fecha de ingreso', 'fecha_ingreso', e.fecha_ingreso || '', 'type="date"') +
    `<label>Su sueldo va en el grupo <select name="letra">${opciones(S.c.grupos.map(x => [x.letra, `${x.letra} - ${x.nombre}`]), e.letra)}</select></label>`,
    async d => {
      await api(`/api/consorcios/${S.c.id}/encargados${id ? '/' + id : ''}`, { metodo: id ? 'PUT' : 'POST', datos: d });
      cerrarModal(); avisar('Encargado guardado.' + (id ? '' : ' Ahora agregale sus conceptos de sueldo.')); irA('consorcio/' + S.c.id);
    });
}

function camposConcepto(f = {}) {
  return `<label>Tipo <select name="tipo">${opciones(Object.entries(TIPOS_SUELDO), f.tipo || 'remuneracion')}</select></label>` +
    campo('Concepto', 'concepto', f.concepto, 'required placeholder="ej. Sueldo básico, Jubilación, F.931"') +
    campo('Importe en pesos', 'importe', plataInput(f.importe), 'required inputmode="decimal"');
}

function modalSueldoFijo(eid, sid) {
  const f = sid ? S.encargados.find(x => x.id === eid).fijos.find(x => x.id === sid) : {};
  formModal(sid ? 'Editar concepto de sueldo' : 'Nuevo concepto de sueldo', camposConcepto(f), async d => {
    await api(`/api/encargados/${eid}/sueldos-fijos${sid ? '/' + sid : ''}`, { metodo: sid ? 'PUT' : 'POST', datos: d });
    cerrarModal(); avisar('Concepto guardado.'); irA('consorcio/' + S.c.id);
  });
}

function modalJuicio(id) {
  const j = id ? S.juicios.find(x => x.id === id) : { visible: 1 };
  formModal(id ? 'Editar juicio' : 'Nuevo juicio',
    campo('Juzgado', 'juzgado', j.juzgado, 'required') + campo('Expediente', 'expediente', j.expediente) +
    campo('Carátula', 'caratula', j.caratula, 'required') +
    campo('Monto reclamado en pesos', 'monto_reclamado', plataInput(j.monto_reclamado), 'inputmode="decimal"') +
    campo('Objeto', 'objeto', j.objeto) + campo('Estado', 'estado', j.estado, 'required placeholder="ej. En trámite"') +
    siNo('Mostrar en las expensas', 'visible', j.visible),
    async d => {
      await api(`/api/consorcios/${S.c.id}/juicios${id ? '/' + id : ''}`, { metodo: id ? 'PUT' : 'POST', datos: d });
      cerrarModal(); avisar('Juicio guardado.'); irA('consorcio/' + S.c.id);
    });
}

/** Los datos del consorcio para leer (sin campos para escribir). */
function fichaConsorcio(c, dosColumnas = false) {
  const sn = v => v ? 'Sí' : 'No';
  return `<dl class="datos${dosColumnas ? ' dos-columnas' : ''}">
      <dt>Nombre</dt><dd>${esc(c.nombre)}</dd>
      <dt>Dirección</dt><dd>${esc(c.direccion)}${c.localidad ? ', ' + esc(c.localidad) : ''}${c.cp ? ' (CP ' + esc(c.cp) + ')' : ''}</dd>
      <dt>CUIT</dt><dd>${esc(c.cuit) || '—'}</dd>
      <dt>Email de las expensas</dt><dd>${esc(c.email) || '<span class="chip rojo">falta cargarlo</span>'}</dd>
      <dt>Clave SUTERH</dt><dd>${esc(c.clave_suterh) || '—'}</dd>
      <dt>Categoría del edificio</dt><dd>${c.categoria ? 'Categoría ' + esc(c.categoria) : '—'}</dd>
      <dt>Año de construcción</dt><dd>${c.anio_construccion || '—'}</dd>
      <dt>Configuración de superficies</dt><dd>${c.superficies === 'absoluta' ? 'Absoluta (m² por unidad)' : 'Porcentual (% por unidad)'}</dd>
      <dt>Interés por mora</dt><dd>${String(c.interes_mora).replace('.', ',')}% mensual</dd>
      <dt>Tipo de interés</dt><dd>${c.tipo_interes === 'compuesto' ? 'Compuesto (cobra interés sobre interés: ' + LINK_ANATOCISMO + ')' : 'Simple (no cobra interés sobre interés, sin ' + LINK_ANATOCISMO + ')'}</dd>
      <dt>Vencimiento</dt><dd>día ${c.dia_vencimiento} del mes siguiente</dd>
      <dt>Mostrar inquilino en el reparto</dt><dd>${sn(c.mostrar_inquilino)}</dd>
      <dt>Envía comprobantes de gastos</dt><dd>${sn(c.envia_comprobantes)}</dd>
      <dt>El pago cancela primero la deuda más vieja</dt><dd>${sn(c.imputa_a_deuda)}</dd>
      <dt>Liquida mes vencido</dt><dd>${sn(c.liquida_mes_vencido)}</dd>
      <dt>Grupos de gastos</dt><dd>${c.grupos.map(g => `${g.letra}: ${esc(g.nombre)}`).join(' · ')}</dd>
      <dt>Nota de las expensas</dt><dd>${esc(c.nota_expensas) || '—'}</dd>
      <dt>Caja inicial</dt><dd>${plata(c.caja_inicial || 0)}</dd>
      <dt>Cuenta bancaria</dt><dd>${c.banco_nombre || c.banco_cbu ? esc([c.banco_titular, c.banco_nombre, c.banco_sucursal && 'sucursal ' + c.banco_sucursal,
        c.banco_cuenta && 'cuenta ' + c.banco_cuenta].filter(Boolean).join(' · ')) : '—'}</dd>
      <dt>CBU y alias</dt><dd>${esc([c.banco_cbu, c.banco_alias].filter(Boolean).join(' · ')) || '—'}</dd>
    </dl>`;
}

/** Desde Inicio: la ficha del consorcio para leer, con un botón para pasar a editarla. */
async function verFicha(id, cantUnidades) {
  try { S.c = await api('/api/consorcios/' + id); } catch (e) { return avisar(e.message, true); }
  S.cantUnidades = cantUnidades;
  abrirModal(`<h2>Ficha de ${esc(S.c.nombre)}</h2>${fichaConsorcio(S.c)}
    <div class="botones"><button class="primario" onclick="modalEditarConsorcio('inicio')">Editar</button>
    <button onclick="cerrarModal()">Cerrar</button></div>`);
  $('#modal-cuerpo h2').setAttribute('tabindex', '-1'); $('#modal-cuerpo h2').focus();
}

function modalEditarConsorcio(volver) {
  formModal('Editar ' + esc(S.c.nombre), camposConsorcio(S.c), async d => {
    if (d.superficies !== S.c.superficies && S.cantUnidades &&
        !confirm('Cambiaste la configuración de superficies. Los números cargados en cada unidad se van a leer como ' +
          (d.superficies === 'absoluta' ? 'metros cuadrados' : 'porcentajes') + '. Revisalos después. ¿Seguir?')) return;
    await api('/api/consorcios/' + S.c.id, { metodo: 'PUT', datos: d });
    await cargarConsorcios(); cerrarModal(); avisar('Datos guardados.'); irA(volver);
    if (volver === 'inicio') verFicha(S.c.id, S.cantUnidades);
  }, { grande: true, intro: AVISO_INTERES });
}

function modalGrupos() {
  const nombre = l => S.c.grupos.find(g => g.letra === l)?.nombre || '';
  formModal('Grupos de gastos', ['A', 'B', 'C', 'D', 'E'].map(l => campo(`Grupo ${l}${l === 'A' ? ' (generales, obligatorio)' : ''}`, l, nombre(l))).join(''),
    async d => {
      await api(`/api/consorcios/${S.c.id}/grupos`, { metodo: 'PUT', datos: Object.entries(d).map(([letra, nombre]) => ({ letra, nombre })) });
      cerrarModal(); avisar('Grupos guardados. Revisá los porcentajes de cada unidad.'); irA('consorcio/' + S.c.id);
    }, { intro: '<p class="sutil">Cada grupo reparte sus gastos con su propio porcentaje por unidad. Ejemplo: A = gastos generales, B = ascensor (solo las unidades que lo usan). Dejar vacío un grupo para no usarlo.</p>' });
}

function modalUnidad(id) {
  const u = id ? S.unidades.find(x => x.id === id) : { tipo: 'vivienda', porcentajes: {} };
  formModal(id ? 'Editar ' + esc(u.nombre) : 'Nueva unidad',
    campo('Nombre (ej. UF 3)', 'nombre', u.nombre, 'required') + campo('Piso', 'piso', u.piso) + campo('Departamento', 'depto', u.depto) +
    `<label>Tipo <select name="tipo">${opciones(Object.entries(TIPOS), u.tipo)}</select></label>` +
    S.c.grupos.map(g => campo(`${S.c.superficies === 'absoluta' ? 'Superficie en m²' : 'Porcentaje'} en grupo ${g.letra} (${esc(g.nombre)})`,
      'pct_' + g.letra, u.porcentajes[g.letra] ?? '', 'inputmode="decimal"')).join(''),
    async d => {
      const porcentajes = {};
      for (const g of S.c.grupos) porcentajes[g.letra] = d['pct_' + g.letra];
      const datos = { nombre: d.nombre, piso: d.piso, depto: d.depto, tipo: d.tipo, porcentajes };
      await api(id ? '/api/unidades/' + id : `/api/consorcios/${S.c.id}/unidades`, { metodo: id ? 'PUT' : 'POST', datos });
      cerrarModal(); avisar('Unidad guardada.'); irA('consorcio/' + S.c.id);
    });
}

async function modalPersonasUnidad(id) {
  const u = S.unidades.find(x => x.id === id);
  const todas = await api('/api/personas');
  abrirModal(`<h2>Personas de ${esc(u.nombre)}</h2>
    <ul>${u.personas.map(p => `<li>${esc(p.apellido)}, ${esc(p.nombre)} (${p.rol})
      <button class="chico peligro" onclick="hacer(api('/api/unidades/${id}/personas/${p.id}/${p.rol}', {metodo:'DELETE'}).then(cerrarModal), 'Quitada.', 'consorcio/${S.c.id}')">Quitar</button></li>`).join('') || '<li class="sutil">Nadie cargado.</li>'}</ul>
    <form id="f-vincular"><div class="campos">
      <label>Persona <select name="persona_id" required>${opciones(todas.map(p => [p.id, `${p.apellido}, ${p.nombre}`]), '', '— elegir —')}</select></label>
      <label>Como <select name="rol">${opciones([['propietario', 'Propietario'], ['inquilino', 'Inquilino']], 'propietario')}</select></label>
    </div><p class="error" role="alert"></p><div class="botones"><button class="primario" type="submit">Agregar</button>
    <button type="button" onclick="cerrarModal(); modalPersona(null, ${id})">Es una persona nueva</button>
    <button type="button" onclick="cerrarModal()">Cerrar</button></div></form>`);
  const f = $('#f-vincular');
  f.addEventListener('submit', async ev => {
    ev.preventDefault();
    try { await api(`/api/unidades/${id}/personas`, { metodo: 'POST', datos: leerForm(f) }); cerrarModal(); avisar('Agregada.'); irA('consorcio/' + S.c.id); }
    catch (e) { $('.error', f).textContent = e.message; }
  });
}

function modalGastoFijo(id) {
  const g = id ? S.fijos.find(x => x.id === id) : { letra: 'A' };
  formModal(id ? 'Editar gasto fijo' : 'Nuevo gasto fijo', camposGasto(g, S.c.grupos, S.provs), async d => {
    await api(`/api/consorcios/${S.c.id}/gastos-fijos${id ? '/' + id : ''}`, { metodo: id ? 'PUT' : 'POST', datos: d });
    cerrarModal(); avisar('Gasto fijo guardado.'); irA('consorcio/' + S.c.id);
  });
}

function camposGasto(g, grupos, provs, conComprobante = false) {
  return `<label>Rubro <select name="rubro_id">${opciones(S.rubros.filter(r => r.activo || r.id === g.rubro_id).map(r => [r.id, `${r.numero}. ${r.nombre}`]), g.rubro_id, '— sin rubro —')}</select></label>` +
    `<label>Grupo <select name="letra">${opciones(grupos.map(x => [x.letra, `${x.letra} - ${x.nombre}`]), g.letra)}</select></label>` +
    campo('Descripción', 'descripcion', g.descripcion, 'required class="ancho"') +
    `<label>Proveedor <select name="proveedor_id">${opciones(provs.filter(p => p.activo || p.id === g.proveedor_id).map(p => [p.id, p.nombre]), g.proveedor_id, '— ninguno —')}</select></label>` +
    (conComprobante ? campo('Comprobante (factura, recibo)', 'comprobante', g.comprobante) + campo('Período de la factura', 'periodo', g.periodo, 'placeholder="ej. 09/2026"') : '') +
    campo('Importe en pesos', 'importe', plataInput(g.importe), 'required inputmode="decimal" placeholder="ej. 125000,50"');
}

// ── PERSONAS ──
VISTAS.personas = async () => {
  const lista = await api('/api/personas');
  S.personas = lista;
  $('#vista').innerHTML = `
    <div class="encabezado"><h2>Propietarios e inquilinos</h2><div class="botones"><button class="primario" onclick="modalPersona()">Nueva persona</button></div></div>
    <label class="buscar">Buscar <input type="search" oninput="filtrar(this.value, '#t-personas')" placeholder="nombre, unidad, teléfono…"></label>
    <div class="tarjeta tabla-wrap"><table id="t-personas"><caption class="sr">Personas</caption>
      <thead><tr><th>Apellido y nombre</th><th>Unidades</th><th>Teléfono</th><th>Email</th><th></th></tr></thead><tbody>
      ${lista.map(p => `<tr><td><b>${esc(p.apellido)}</b>, ${esc(p.nombre)}</td>
        <td>${p.unidades.map(u => `${esc(u.nombre)} de ${esc(u.consorcio)} <span class="sutil">(${u.rol})</span>`).join('<br>') || '<span class="sutil">ninguna</span>'}</td>
        <td>${esc(p.telefono)}</td><td>${esc(p.email)}</td>
        <td><button class="chico" onclick="modalPersona(${p.id})">Editar</button></td></tr>`).join('')}
    </tbody></table></div>`;
};

function filtrar(texto, tabla) {
  const t = texto.trim().toLowerCase();
  document.querySelectorAll(tabla + ' tbody tr').forEach(tr => tr.classList.toggle('oculto', t && !tr.textContent.toLowerCase().includes(t)));
}

function modalPersona(id, unidadId) {
  const p = id ? S.personas.find(x => x.id === id) : {};
  formModal(id ? 'Editar ' + esc(p.apellido) : 'Nueva persona',
    campo('Nombre', 'nombre', p.nombre, 'required') + campo('Apellido', 'apellido', p.apellido, 'required') + campo('DNI', 'dni', p.dni) +
    campo('Teléfono', 'telefono', p.telefono, 'type="tel"') + campo('Email', 'email', p.email, 'type="email"') + campo('Dirección', 'direccion', p.direccion) +
    (unidadId ? `<label>Como <select name="rol">${opciones([['propietario', 'Propietario'], ['inquilino', 'Inquilino']], 'propietario')}</select></label>` : '') +
    `<label class="ancho">Nota <textarea name="nota">${esc(p.nota || '')}</textarea></label>`,
    async d => {
      const r = await api(id ? '/api/personas/' + id : '/api/personas', { metodo: id ? 'PUT' : 'POST', datos: d });
      if (unidadId) await api(`/api/unidades/${unidadId}/personas`, { metodo: 'POST', datos: { persona_id: r.id, rol: d.rol } });
      cerrarModal(); avisar('Persona guardada.'); irA(unidadId ? 'consorcio/' + S.c.id : 'personas');
    });
}

// ── PROVEEDORES ──
VISTAS.proveedores = async () => {
  const lista = await api('/api/proveedores');
  S.provs = lista;
  $('#vista').innerHTML = `
    <div class="encabezado"><h2>Proveedores</h2><div class="botones"><button class="primario" onclick="modalProveedor()">Nuevo proveedor</button></div></div>
    <div class="tarjeta tabla-wrap"><table><caption class="sr">Proveedores</caption><thead><tr><th>Nombre</th><th>Rubro</th><th>CUIT</th><th>Teléfono</th><th></th></tr></thead><tbody>
      ${lista.map(p => `<tr class="${p.activo ? '' : 'baja'}"><td>${esc(p.nombre)}</td><td>${esc(p.rubro)}</td><td>${esc(p.cuit)}</td><td>${esc(p.telefono)}</td>
        <td class="botones"><button class="chico" onclick="modalProveedor(${p.id})">Editar</button>
        <button class="chico ${p.activo ? 'peligro' : ''}" onclick="hacer(api('/api/proveedores/${p.id}/${p.activo ? 'baja' : 'alta'}', {metodo:'POST'}), null, 'proveedores')">${p.activo ? 'Dar de baja' : 'Reactivar'}</button></td></tr>`).join('')}
    </tbody></table></div>`;
};

function modalProveedor(id) {
  const p = id ? S.provs.find(x => x.id === id) : {};
  formModal(id ? 'Editar proveedor' : 'Nuevo proveedor',
    campo('Nombre', 'nombre', p.nombre, 'required') + campo('Rubro', 'rubro', p.rubro) + campo('CUIT', 'cuit', p.cuit) + campo('Teléfono', 'telefono', p.telefono, 'type="tel"'),
    async d => { await api(id ? '/api/proveedores/' + id : '/api/proveedores', { metodo: id ? 'PUT' : 'POST', datos: d }); cerrarModal(); avisar('Proveedor guardado.'); irA('proveedores'); });
}

// ── EXPENSAS ──
VISTAS.expensas = async () => {
  if (!S.consorcio) { $('#vista').innerHTML = `<h2>Expensas</h2>${elegirConsorcio('expensas')}`; return; }
  const lista = await api(`/api/consorcios/${S.consorcio}/liquidaciones`);
  const abierta = lista.find(l => l.estado === 'abierta');
  $('#vista').innerHTML = `
    <div class="encabezado"><h2>Expensas</h2>${elegirConsorcio('expensas')}
      <div class="botones">${abierta ? '' : '<button class="primario" onclick="modalAbrirLiquidacion()">Abrir liquidación del mes</button>'}</div></div>
    <p class="sutil">Cada mes: se abre la liquidación, se cargan los gastos, se revisa el reparto y se cierra. Al cerrar queda la deuda de cada unidad.</p>
    <div class="tarjeta tabla-wrap"><table><caption class="sr">Liquidaciones</caption><thead><tr><th>Mes</th><th>Estado</th><th>Gastos</th><th>Total</th><th>Vence</th><th></th></tr></thead><tbody>
      ${lista.map(l => `<tr><td><a href="#liquidacion/${l.id}">${esc(l.nombre)}</a></td>
        <td>${l.estado === 'abierta' ? '<span class="chip ambar">Abierta</span>' : '<span class="chip verde">Cerrada</span>'}</td>
        <td>${l.cantidad_gastos}</td><td class="num">${plata(l.total_gastos)}</td><td>${fecha(l.vencimiento)}</td>
        <td><button class="chico" onclick="irA('liquidacion/${l.id}')">Abrir</button></td></tr>`).join('') || '<tr><td colspan="6" class="sutil">Todavía no hay liquidaciones.</td></tr>'}
    </tbody></table></div>`;
};

function modalAbrirLiquidacion() {
  const d = new Date(); const mes = `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}`;
  formModal('Abrir liquidación', `<label>Mes de los gastos <input type="month" name="periodo" value="${mes}" required></label>
    <label class="ancho">Nota (opcional) <textarea name="nota"></textarea></label>`, async d => {
    const l = await api(`/api/consorcios/${S.consorcio}/liquidaciones`, { metodo: 'POST', datos: d });
    cerrarModal(); avisar('Liquidación abierta, con los gastos fijos ya cargados.'); irA('liquidacion/' + l.id);
  }, { boton: 'Abrir', intro: '<p class="sutil">Se copian automáticamente los gastos fijos del consorcio.</p>' });
}

const pct = (parte, total) => total ? (parte * 100 / total).toLocaleString('es-AR', { minimumFractionDigits: 2, maximumFractionDigits: 2 }) + '%' : '';
const pisoDepto = f => esc([f.piso, f.depto].filter(Boolean).join(' '));

/** Reparto por unidad, con las mismas columnas que la liquidación de ACON. */
function tablaProrrateo(l) {
  const letras = l.grupos.map(g => g.letra);
  const tot = k => l.prorrateo.reduce((s, f) => s + (k(f) || 0), 0);
  const inq = !!l.consorcio.mostrar_inquilino;
  const m2 = l.consorcio.superficies === 'absoluta';
  const coef = (f, x) => {   // % de la unidad en el grupo: el porcentaje cargado, o su parte de los m²
    const total = l.totales[x] || 0;
    return total ? ((f.por_grupo[x] || 0) * 100 / total).toLocaleString('es-AR', { maximumFractionDigits: 2 }) : '';
  };
  return `<table class="prorrateo"><caption class="sr">Estado de cuentas y prorrateo de gastos</caption><thead><tr>
    <th>UF</th><th>Propietario</th>${inq ? '<th>Inquilino</th>' : ''}
    <th class="num">Saldo deudor</th><th class="num">Pagos</th><th class="num">Anulaciones y ajustes</th><th class="num">Deuda</th><th class="num">Interés por mora</th>
    ${letras.map(x => `<th class="num">% ${x}${m2 ? ' (por m²)' : ''}</th><th class="num">Gastos ${x}</th>`).join('')}
    <th class="num">Gastos particulares</th><th class="num">Redondeo</th><th class="num">Total</th></tr></thead><tbody>
    ${l.prorrateo.map(f => `<tr><td><b>${esc(f.nombre)}</b> ${pisoDepto(f)}</td><td>${esc(f.propietarios)}</td>${inq ? `<td>${esc(f.inquilinos)}</td>` : ''}
      <td class="num">${plata(f.saldo_deudor)}</td><td class="num">${plata(f.pagos)}</td><td class="num">${plata(f.ajustes)}</td>
      <td class="num">${plata(f.saldo_anterior)}</td><td class="num">${plata(f.interes)}</td>
      ${letras.map(x => `<td class="num">${coef(f, x)}</td><td class="num">${plata(f.por_grupo[x] || 0)}</td>`).join('')}
      <td class="num">${plata(f.particulares)}</td><td class="num">${plata(f.redondeo)}</td><td class="num"><b>${plata(f.total)}</b></td></tr>`).join('')}
    </tbody><tfoot><tr><th colspan="${inq ? 3 : 2}">Totales</th><th class="num">${plata(tot(f => f.saldo_deudor))}</th><th class="num">${plata(tot(f => f.pagos))}</th>
      <th class="num">${plata(tot(f => f.ajustes))}</th><th class="num">${plata(tot(f => f.saldo_anterior))}</th><th class="num">${plata(tot(f => f.interes))}</th>
      ${letras.map(x => `<th class="num">100%</th><th class="num">${plata(tot(f => f.por_grupo[x]))}</th>`).join('')}
      <th class="num">${plata(tot(f => f.particulares))}</th><th class="num">${plata(tot(f => f.redondeo))}</th><th class="num">${plata(tot(f => f.total))}</th></tr></tfoot></table>
    ${l.consorcio.interes_mora ? `<p class="sutil">Tasa de interés punitorio aplicada para casos de morosidad: ${String(l.consorcio.interes_mora).replace('.', ',')}% mensual (${l.consorcio.tipo_interes}).</p>` : ''}`;
}

/** Total general de gastos del mes (lo que se reparte + los particulares). */
const totalGeneral = l => Object.values(l.totales).reduce((a, b) => a + b, 0) + l.total_particulares;

/** Gastos agrupados por rubro, con columnas por grupo, total del rubro y % del total (como la Ley 941). */
function tablaRubros(l, editable) {
  const letras = l.grupos.map(g => g.letra), total = totalGeneral(l);
  const porRubro = new Map();
  for (const g of l.gastos) {
    const clave = g.rubro_numero ?? 99;
    if (!porRubro.has(clave)) porRubro.set(clave, { titulo: g.rubro ? `${g.rubro_numero}. ${g.rubro}` : 'Sin rubro', items: [] });
    porRubro.get(clave).items.push(g);
  }
  const col = letras.length + (editable ? 5 : 4);
  const filasRubro = [...porRubro.entries()].sort((a, b) => a[0] - b[0]).map(([, r]) => {
    const sub = r.items.reduce((s, g) => s + g.importe, 0);
    return `<tr class="rubro"><th colspan="${col}" scope="colgroup">${esc(r.titulo)}</th></tr>
      ${r.items.map(g => `<tr><td>${esc(g.descripcion)}${g.proveedor ? ` <span class="sutil">· ${esc(g.proveedor)}</span>` : ''}${g.comprobante ? ` <span class="sutil">· ${esc(g.comprobante)}</span>` : ''}</td>
        <td>${esc(g.periodo)}</td>${letras.map(x => `<td class="num">${g.letra === x ? plata(g.importe) : ''}</td>`).join('')}<td class="num">${plata(g.importe)}</td>
        ${editable ? `<td class="botones no-imprimir"><button class="chico" onclick="modalGasto(${g.id})">Editar</button>
          <button class="chico peligro" onclick="if(confirm('¿Borrar este gasto?')) hacer(api('/api/gastos/${g.id}', {metodo:'DELETE'}), 'Gasto borrado.', 'liquidacion/${l.id}')">Borrar</button></td>` : ''}</tr>`).join('')}
      <tr class="subtotal"><td colspan="${letras.length + 2}">Total del rubro <span class="sutil">(${pct(sub, total)} del total)</span></td><td class="num">${plata(sub)}</td>${editable ? '<td></td>' : ''}</tr>`;
  }).join('');
  return `<table class="rubros"><caption class="sr">Gastos del mes por rubro</caption><thead><tr><th>Concepto</th><th>Período</th>
    ${letras.map(x => `<th class="num">Gastos ${x}</th>`).join('')}<th class="num">Total</th>${editable ? '<th class="no-imprimir"></th>' : ''}</tr></thead>
    <tbody>${filasRubro || `<tr><td colspan="${col}" class="sutil">Sin gastos cargados.</td></tr>`}</tbody></table>`;
}

/** Remuneraciones al personal: por encargado, remuneraciones, descuentos y aportes, en el grupo que corresponde. */
function tablaPersonal(l, editable) {
  if (!l.personal.length) return '<p class="sutil">Sin sueldos cargados este mes.</p>';
  const total = totalGeneral(l);
  return l.personal.map(p => {
    const e = p.encargado;
    const fila = i => `<tr><td>${TIPOS_SUELDO[i.tipo].split(' (')[0]}</td><td>${esc(i.concepto)}</td>
      <td class="num">${i.tipo === 'descuento' ? '−' + plata(i.importe) : plata(i.importe)}</td>
      ${editable ? `<td class="botones no-imprimir"><button class="chico" onclick="modalSueldo(${i.id})">Editar</button>
        <button class="chico peligro" onclick="if(confirm('¿Borrar este concepto?')) hacer(api('/api/sueldos/${i.id}', {metodo:'DELETE'}), 'Concepto borrado.', 'liquidacion/${l.id}')">Borrar</button></td>` : ''}</tr>`;
    return `<div class="bloque"><p><b>${esc(e.apellido)}, ${esc(e.nombre)}</b> · CUIL ${esc(e.cuil) || '—'} · Cargo: ${esc(e.cargo) || '—'} ·
        Categoría del encargado: ${esc(e.categoria) || '—'} · Categoría del edificio: ${l.consorcio.categoria ? 'Categoría ' + esc(l.consorcio.categoria) : '—'} ·
        Período: ${esc(l.nombre)} · Grupo ${e.letra}</p>
      <table><caption class="sr">Sueldo de ${esc(e.apellido)}</caption><thead><tr><th>Tipo</th><th>Concepto</th><th class="num">Importe</th>${editable ? '<th class="no-imprimir"></th>' : ''}</tr></thead><tbody>
      ${p.items.map(fila).join('')}</tbody><tfoot>
      <tr><th colspan="2">Neto (remuneraciones − descuentos)</th><th class="num">${plata(p.neto)}</th>${editable ? '<th></th>' : ''}</tr>
      <tr><th colspan="2">Aportes y contribuciones</th><th class="num">${plata(p.aportes)}</th>${editable ? '<th></th>' : ''}</tr>
      <tr><th colspan="2">Total del rubro 1 <span class="sutil">(${pct(p.total, total)} del total)</span></th><th class="num">${plata(p.total)}</th>${editable ? '<th></th>' : ''}</tr></tfoot></table></div>`;
  }).join('');
}

function tablaParticulares(l, editable) {
  return `<table><caption class="sr">Gastos particulares</caption><thead><tr><th>Unidad</th><th>Descripción</th><th class="num">Importe</th>${editable ? '<th class="no-imprimir"></th>' : ''}</tr></thead><tbody>
    ${l.particulares.map(g => `<tr><td>${esc(g.unidad)} ${pisoDepto(g)}</td><td>${esc(g.descripcion)}</td><td class="num">${plata(g.importe)}</td>
      ${editable ? `<td class="botones no-imprimir"><button class="chico" onclick="modalParticular(${g.id})">Editar</button>
        <button class="chico peligro" onclick="if(confirm('¿Borrar este gasto particular?')) hacer(api('/api/particulares/${g.id}', {metodo:'DELETE'}), 'Borrado.', 'liquidacion/${l.id}')">Borrar</button></td>` : ''}</tr>`).join('')
      || `<tr><td colspan="4" class="sutil">No hay gastos particulares.</td></tr>`}</tbody></table>`;
}

/** Caja (ingresos y egresos) y estado patrimonial, cuando la liquidación está cerrada. */
function tablaCaja(l) {
  if (!l.caja) return '<p class="sutil">Se calcula al cerrar la liquidación.</p>';
  const k = l.caja, cierre = fecha((l.cerrada_en || '').slice(0, 10));
  return `<table class="caja"><caption class="sr">Detalle de egresos e ingresos</caption><tbody>
    <tr class="subtotal"><td>Saldo anterior de la caja</td><td class="num">${plata(k.anterior)}</td></tr>
    <tr><td>Ingresos por pagos de expensas</td><td class="num">${plata(k.ingresos)}</td></tr>
    ${l.grupos.map(g => `<tr><td>Egresos por gastos del mes "${g.letra}"</td><td class="num">−${plata(k.egresos_por_grupo[g.letra] || 0)}</td></tr>`).join('')}
    <tr><td>Egresos por gastos particulares</td><td class="num">−${plata(k.egresos_particulares)}</td></tr>
    <tr class="subtotal"><td>Saldo final al ${cierre}</td><td class="num"><b>${plata(k.final)}</b></td></tr></tbody></table>
    <h4>Estado patrimonial</h4>
    <table class="caja"><caption class="sr">Estado patrimonial</caption><tbody>
    <tr><td>Saldo de disponibilidades al cierre (${cierre})</td><td class="num">${plata(l.patrimonio.disponibilidades)}</td></tr>
    <tr><td>Expensas y otros conceptos a cobrar</td><td class="num">${plata(l.patrimonio.a_cobrar)}</td></tr>
    <tr class="subtotal"><td>Patrimonio neto al cierre</td><td class="num"><b>${plata(l.patrimonio.neto)}</b></td></tr></tbody></table>`;
}

VISTAS.liquidacion = async id => {
  const [l, provs, rubros, encargados] = await Promise.all([api('/api/liquidaciones/' + id), api('/api/proveedores'), api('/api/rubros'), null]);
  S.l = l; S.provs = provs; S.rubros = rubros; S.consorcio = l.consorcio_id;
  const abierta = l.estado === 'abierta';
  if (abierta) {
    [S.encargados, S.unidadesLiq] = await Promise.all([api(`/api/consorcios/${l.consorcio_id}/encargados`), api(`/api/consorcios/${l.consorcio_id}/unidades`)]);
  }
  $('#vista').innerHTML = `
    <div class="encabezado"><h2>Expensas de ${esc(l.nombre)} · ${esc(l.consorcio.nombre)}</h2>
      <div class="botones">
        ${abierta ? `<button onclick="modalCerrar()">Cerrar liquidación</button>
          <button onclick="imprimirLiquidacion()">Vista previa para imprimir</button>
          <button class="peligro" onclick="if(confirm('¿Descartar esta liquidación abierta con todos sus gastos?')) hacer(api('/api/liquidaciones/${l.id}', {metodo:'DELETE'}), 'Liquidación descartada.', 'expensas')">Descartar</button>`
        : `<button class="primario" onclick="imprimirLiquidacion()">Imprimir o guardar PDF</button>
          <button onclick="if(confirm('¿Reabrir? Se borra el reparto para poder corregir gastos y después hay que volver a cerrarla.')) hacer(api('/api/liquidaciones/${l.id}/reabrir', {metodo:'POST'}), 'Liquidación reabierta.', 'liquidacion/${l.id}')">Reabrir para corregir</button>`}
        <button onclick="irA('expensas')">Volver</button></div></div>
    <p>${abierta ? '<span class="chip ambar">Abierta</span> Todavía se pueden cambiar los gastos. El reparto de abajo es una vista previa.'
      : `<span class="chip verde">Cerrada</span> Vence el ${fecha(l.vencimiento)}.`}
      Total de gastos del mes: <b>${plata(totalGeneral(l))}</b>.</p>
    ${l.avisos.map(a => `<p class="error" role="alert">${esc(a)}</p>`).join('')}
    <section class="tarjeta"><div class="encabezado"><h3>1. Remuneraciones al personal</h3>
      ${abierta && S.encargados.some(e => e.activo) ? '<div class="botones"><button onclick="modalSueldo()">Agregar concepto de sueldo</button></div>' : ''}</div>
      <div class="tabla-wrap">${tablaPersonal(l, abierta)}</div></section>
    <section class="tarjeta"><div class="encabezado"><h3>Gastos por rubro</h3>
      ${abierta ? '<div class="botones"><button class="primario" onclick="modalGasto()">Agregar gasto</button></div>' : ''}</div>
      <div class="tabla-wrap">${tablaRubros(l, abierta)}</div></section>
    <section class="tarjeta"><div class="encabezado"><h3>Gastos particulares (de una sola unidad)</h3>
      ${abierta ? '<div class="botones"><button onclick="modalParticular()">Agregar gasto particular</button></div>' : ''}</div>
      <div class="tabla-wrap">${tablaParticulares(l, abierta)}</div></section>
    <section class="tarjeta"><h3>Estado de cuentas y reparto por unidad${abierta ? ' (vista previa)' : ''}</h3>
      <div class="tabla-wrap">${l.prorrateo.length ? tablaProrrateo(l) : '<p class="sutil">Sin reparto.</p>'}</div></section>
    <section class="tarjeta"><h3>Detalle de egresos e ingresos (caja)</h3><div class="tabla-wrap">${tablaCaja(l)}</div></section>`;
};

function modalGasto(id) {
  const g = id ? S.l.gastos.find(x => x.id === id) : { letra: 'A' };
  formModal(id ? 'Editar gasto' : 'Agregar gasto', camposGasto(g, S.l.grupos, S.provs, true), async d => {
    await api(`/api/liquidaciones/${S.l.id}/gastos${id ? '/' + id : ''}`, { metodo: id ? 'PUT' : 'POST', datos: d });
    cerrarModal(); avisar('Gasto guardado.'); irA('liquidacion/' + S.l.id);
  });
}

function modalParticular(id) {
  const g = id ? S.l.particulares.find(x => x.id === id) : {};
  const unidades = S.unidadesLiq.unidades.filter(u => u.activa);
  formModal(id ? 'Editar gasto particular' : 'Agregar gasto particular',
    `<label>Unidad <select name="unidad_id" required>${opciones(unidades.map(u => [u.id, `${u.nombre} ${[u.piso, u.depto].filter(Boolean).join(' ')}`]), g.unidad_id, '— elegir —')}</select></label>` +
    campo('Descripción', 'descripcion', g.descripcion, 'required placeholder="ej. Arreglo de cañería de la unidad"') +
    campo('Importe en pesos', 'importe', plataInput(g.importe), 'required inputmode="decimal"'),
    async d => {
      await api(`/api/liquidaciones/${S.l.id}/particulares${id ? '/' + id : ''}`, { metodo: id ? 'PUT' : 'POST', datos: d });
      cerrarModal(); avisar('Gasto particular guardado.'); irA('liquidacion/' + S.l.id);
    }, { intro: '<p class="sutil">Se le cobra entero a esa unidad, no se reparte entre las demás.</p>' });
}

function modalSueldo(id) {
  const item = id ? S.l.personal.flatMap(p => p.items).find(x => x.id === id) : {};
  const activos = S.encargados.filter(e => e.activo || e.id === item.encargado_id);
  formModal(id ? 'Editar concepto de sueldo' : 'Agregar concepto de sueldo',
    `<label>Encargado <select name="encargado_id" required>${opciones(activos.map(e => [e.id, `${e.apellido}, ${e.nombre}`]), item.encargado_id ?? activos[0]?.id)}</select></label>` +
    camposConcepto(item),
    async d => {
      await api(`/api/liquidaciones/${S.l.id}/sueldos${id ? '/' + id : ''}`, { metodo: id ? 'PUT' : 'POST', datos: d });
      cerrarModal(); avisar('Concepto guardado.'); irA('liquidacion/' + S.l.id);
    });
}

function modalCerrar() {
  const [a, m] = S.l.periodo.split('-').map(Number);
  const sig = new Date(a, m, S.l.consorcio.dia_vencimiento);
  const vence = `${sig.getFullYear()}-${String(sig.getMonth() + 1).padStart(2, '0')}-${String(sig.getDate()).padStart(2, '0')}`;
  formModal('Cerrar liquidación de ' + esc(S.l.nombre), `<label>Fecha de vencimiento <input type="date" name="vencimiento" value="${vence}" required></label>`,
    async d => { await api(`/api/liquidaciones/${S.l.id}/cerrar`, { metodo: 'POST', datos: d }); cerrarModal(); avisar('Liquidación cerrada: ya figura la deuda de cada unidad.'); irA('liquidacion/' + S.l.id); },
    { boton: 'Cerrar liquidación', intro: '<p>Al cerrar se calcula y se guarda lo que debe pagar cada unidad, con el interés por mora de quienes deben, y la caja del mes. Después ya no se pueden cambiar los gastos (salvo reabriéndola).</p>' });
}

/** La liquidación impresa, con las secciones y el orden de la Ley 941 (como la de ACON). */
function imprimirLiquidacion() {
  const l = S.l, c = l.consorcio, a = l.administracion;
  const dato = (t, v) => v ? `<div><span>${t}:</span> ${esc(v)}</div>` : '';
  const seccion = (titulo, ley = '') => `<h2 class="banda">${titulo}</h2>${ley ? `<p class="ley">(${ley})</p>` : ''}`;
  imprimir(`Expensas ${l.nombre} - ${c.nombre}`, `<div class="liq">
    <h1 class="banda">EXPENSAS · Liquidación de ${esc(l.nombre)}${l.estado === 'abierta' ? ' · BORRADOR (sin cerrar)' : ` · Vence el ${fecha(l.vencimiento)}`}</h1>
    <div class="cabecera">
      <div><h3>Administración</h3>${dato('Nombre', a.nombre)}${dato('Domicilio', a.domicilio)}${dato('Horarios', a.horarios)}${dato('CUIT', a.cuit)}
        ${dato('Teléfono', a.telefono)}${dato('Email', a.email)}${dato('Inscripción R.P.A.', a.inscripcion_rpa)}${dato('Situación fiscal', a.situacion_fiscal)}</div>
      <div><h3>Consorcio</h3>${dato('Nombre', c.nombre)}${dato('Domicilio', c.direccion)}${dato('Localidad', c.localidad)}${dato('CUIT', c.cuit)}
        ${dato('Clave SUTERH', c.clave_suterh)}</div>
    </div>
    ${seccion('Remuneraciones al personal', 'Conf. Art. 10 inc. d Ley N° 941')}${tablaPersonal(l, false)}
    ${seccion('Pagos del período por suministros, servicios, abonos y seguros', 'Conf. Art. 10 inc. e y f Ley N° 941')}${tablaRubros(l, false)}
    <table class="rubros"><tbody><tr class="total-general"><td>TOTAL GENERAL DE GASTOS</td>${l.grupos.map(g => `<td class="num">${g.letra}: ${plata(l.totales[g.letra] || 0)}</td>`).join('')}
      <td class="num">Particulares: ${plata(l.total_particulares)}</td><td class="num"><b>${plata(totalGeneral(l))}</b></td></tr></tbody></table>
    ${seccion('Estado de cuentas y prorrateo de gastos')}${l.prorrateo.length ? tablaProrrateo(l) : ''}
    ${seccion('Detalle de egresos e ingresos', 'Conf. Art. 10 inc. c Ley N° 941')}${tablaCaja(l)}
    ${seccion('Datos de juicios', 'Conf. Art. 10 inc. h Ley N° 941')}
    ${l.juicios.length ? `<table><thead><tr><th>Juzgado</th><th>Expediente</th><th>Carátula</th><th>Objeto</th><th class="num">Monto reclamado</th><th>Estado</th></tr></thead><tbody>
      ${l.juicios.map(j => `<tr><td>${esc(j.juzgado)}</td><td>${esc(j.expediente)}</td><td>${esc(j.caratula)}</td><td>${esc(j.objeto)}</td>
        <td class="num">${j.monto_reclamado != null ? plata(j.monto_reclamado) : ''}</td><td>${esc(j.estado)}</td></tr>`).join('')}</tbody></table>` : '<p>No hay juicios.</p>'}
    ${seccion('Notas')}
    <ul>${l.grupos.map(g => `<li>Gastos ${g.letra}: ${esc(g.nombre)}</li>`).join('')}</ul>
    ${c.nota_expensas ? `<p>${esc(c.nota_expensas)}</p>` : ''}${l.nota ? `<p>${esc(l.nota)}</p>` : ''}
    ${l.particulares.length ? `<h3>Detalle de gastos particulares por unidad</h3><ul>${l.particulares.map(g => `<li>${esc(g.unidad)} ${pisoDepto(g)}: ${esc(g.descripcion)} ${plata(g.importe)}</li>`).join('')}</ul>` : ''}
    ${seccion('Formas de pago')}
    <div class="cabecera"><div><h3>Depósito o transferencia</h3>${dato('Titular', c.banco_titular)}${dato('CBU', c.banco_cbu)}${dato('Alias', c.banco_alias)}${dato('N° de cuenta', c.banco_cuenta)}</div>
      <div><h3>&nbsp;</h3>${dato('Banco', c.banco_nombre)}${dato('Sucursal', c.banco_sucursal)}${dato('Código de pago electrónico', c.codigo_pago)}</div></div>
  </div>`);
}

// ── COBROS ──
VISTAS.cobros = async () => {
  if (!S.consorcio) { $('#vista').innerHTML = `<h2>Cobros</h2>${elegirConsorcio('cobros')}`; return; }
  const [saldos, pagos] = await Promise.all([api(`/api/consorcios/${S.consorcio}/saldos`), api(`/api/consorcios/${S.consorcio}/pagos`)]);
  S.saldos = saldos;
  $('#vista').innerHTML = `
    <div class="encabezado"><h2>Cobros</h2>${elegirConsorcio('cobros')}</div>
    <section class="tarjeta"><h3>Registrar un pago</h3>
      <form id="f-pago"><div class="campos">
        <label class="ancho">Unidad <select name="unidad" required>${opciones(saldos.map(s => [s.id, `${s.nombre} ${[s.piso, s.depto].filter(Boolean).join(' ')} - ${s.propietarios || 'sin propietario'} - debe ${plata(s.saldo)}`]), '', '— elegir la unidad —')}</select></label>
        ${campo('Importe en pesos', 'importe', '', 'required inputmode="decimal" placeholder="ej. 150000"')}
        ${campo('Fecha del pago', 'fecha', hoyISO(), 'type="date" required')}
        <label>Forma de pago <select name="modalidad">${opciones(MODALIDADES.map(m => [m, m[0].toUpperCase() + m.slice(1)]), 'efectivo')}</select></label>
        ${campo('Quién pagó (si no es el propietario)', 'pago_quien')}
        ${campo('Nota', 'nota', '', 'class="ancho"')}
      </div><p id="pago-saldo" class="sutil" aria-live="polite"></p><p class="error" role="alert"></p>
      <div class="botones"><button class="primario" type="submit">Registrar pago y hacer recibo</button></div></form></section>
    <section class="tarjeta tabla-wrap"><h3>Últimos pagos</h3><table><caption class="sr">Pagos registrados</caption><thead><tr><th>Recibo</th><th>Fecha</th><th>Unidad</th><th>Forma</th><th>Importe</th><th></th></tr></thead><tbody>
      ${pagos.slice(0, 50).map(p => `<tr class="${p.anulado ? 'baja' : ''}"><td>${p.recibo_numero}</td><td>${fecha(p.fecha)}</td><td>${esc(p.unidad)}</td><td>${esc(p.modalidad)}</td><td class="num">${plata(p.importe)}</td>
        <td class="botones"><button class="chico" onclick="verRecibo(${p.id})">Recibo</button>
        ${p.anulado ? '<span class="chip rojo">Anulado</span>' : `<button class="chico peligro" onclick="if(confirm('¿Anular el recibo ${p.recibo_numero}? El pago deja de contar.')) hacer(api('/api/pagos/${p.id}/anular', {metodo:'POST'}), 'Pago anulado.', 'cobros')">Anular</button>`}</td></tr>`).join('') || '<tr><td colspan="6" class="sutil">Sin pagos.</td></tr>'}
    </tbody></table></section>`;
  const f = $('#f-pago');
  f.unidad.addEventListener('change', () => {
    const s = saldos.find(x => String(x.id) === f.unidad.value);
    $('#pago-saldo').textContent = s ? `Saldo actual: ${plata(s.saldo)}${s.vencido ? ` (vencido: ${plata(s.vencido)})` : ''}.` : '';
    if (s && s.saldo > 0 && !f.importe.value) f.importe.value = plataInput(s.saldo);
  });
  f.addEventListener('submit', async ev => {
    ev.preventDefault();
    const d = leerForm(f), b = $('button[type=submit]', f);
    $('.error', f).textContent = ''; b.disabled = true;
    try {
      const r = await api(`/api/unidades/${d.unidad}/pagos`, { metodo: 'POST', datos: d });
      avisar(`Pago registrado. Recibo número ${r.recibo_numero}.`); irA('cobros'); mostrarRecibo(r);
    } catch (e) { $('.error', f).textContent = e.message; } finally { b.disabled = false; }
  });
};

async function verRecibo(id) { mostrarRecibo(await api('/api/pagos/' + id)); }

function htmlRecibo(r) {
  return `<div class="recibo"><h2>Recibo Nº ${r.recibo_numero}${r.anulado ? ' — ANULADO' : ''}</h2>
    <p><b>${esc(r.consorcio)}</b> · ${esc(r.direccion)}</p>
    <dl class="datos"><dt>Fecha</dt><dd>${fecha(r.fecha)}</dd>
      <dt>Unidad</dt><dd>${esc(r.unidad)} ${esc([r.piso, r.depto].filter(Boolean).join(' '))}</dd>
      <dt>Propietario</dt><dd>${esc(r.propietarios)}</dd>
      ${r.pago_quien ? `<dt>Pagó</dt><dd>${esc(r.pago_quien)}</dd>` : ''}
      <dt>Forma de pago</dt><dd>${esc(r.modalidad)}</dd>
      <dt>Importe recibido</dt><dd><b>${plata(r.importe)}</b></dd>
      ${r.nota ? `<dt>Nota</dt><dd>${esc(r.nota)}</dd>` : ''}
      <dt>Saldo de la unidad</dt><dd>${plata(r.saldo_actual)}</dd></dl></div>`;
}
function mostrarRecibo(r) {
  S.recibo = r;
  abrirModal(htmlRecibo(r) + `<div class="botones"><button class="primario" onclick="imprimir('Recibo ${r.recibo_numero}', htmlRecibo(S.recibo))">Imprimir o guardar PDF</button>
    <button onclick="cerrarModal()">Cerrar</button></div>`);
}

// ── SALDOS, MOROSOS Y CUENTA CORRIENTE ──
VISTAS.saldos = async () => {
  if (!S.consorcio) { $('#vista').innerHTML = `<h2>Saldos y morosos</h2>${elegirConsorcio('saldos')}`; return; }
  const [saldos, morosos] = await Promise.all([api(`/api/consorcios/${S.consorcio}/saldos`), api('/api/morosos')]);
  $('#vista').innerHTML = `
    <div class="encabezado"><h2>Saldos y morosos</h2>${elegirConsorcio('saldos')}</div>
    <section class="tarjeta tabla-wrap"><h3>Saldo de cada unidad</h3><table><caption class="sr">Saldos por unidad</caption><thead><tr><th>Unidad</th><th>Propietario</th><th>Saldo</th><th>Vencido</th><th>Último pago</th><th></th></tr></thead><tbody>
      ${saldos.map(s => `<tr><td><b>${esc(s.nombre)}</b> ${esc([s.piso, s.depto].filter(Boolean).join(' '))}</td><td>${esc(s.propietarios)}</td>
        <td class="num">${plata(s.saldo)}</td><td class="num">${s.vencido ? `<span class="chip rojo">${plata(s.vencido)}</span>` : '—'}</td><td>${fecha(s.ultimo_pago) || 'nunca'}</td>
        <td><button class="chico" onclick="irA('cuenta/${s.id}')">Cuenta corriente</button></td></tr>`).join('')}
    </tbody></table><p class="sutil">Saldo positivo = debe. Negativo = tiene saldo a favor. "Vencido" es la parte de la deuda que pasó su fecha de vencimiento.</p></section>
    <section class="tarjeta tabla-wrap"><h3>Morosos de todos los consorcios (${morosos.length})</h3><table><caption class="sr">Morosos</caption><thead><tr><th>Consorcio</th><th>Unidad</th><th>Propietario</th><th>Deuda vencida</th><th>Último pago</th><th></th></tr></thead><tbody>
      ${morosos.map(m => `<tr><td>${esc(m.consorcio)}</td><td>${esc(m.nombre)}</td><td>${esc(m.propietarios)}</td><td class="num">${plata(m.vencido)}</td><td>${fecha(m.ultimo_pago) || 'nunca'}</td>
        <td><button class="chico" onclick="irA('cuenta/${m.id}')">Cuenta corriente</button></td></tr>`).join('') || '<tr><td colspan="6" class="sutil">No hay morosos.</td></tr>'}
    </tbody></table></section>`;
};

VISTAS.cuenta = async id => {
  const u = await api(`/api/unidades/${id}/cuenta`);
  S.cuenta = u;
  $('#vista').innerHTML = `
    <div class="encabezado"><h2>Cuenta corriente · ${esc(u.nombre)} · ${esc(u.consorcio)}</h2>
      <div class="botones"><button class="primario" onclick="imprimir('Cuenta corriente ${esc(u.nombre)}', htmlCuenta(S.cuenta))">Imprimir o guardar PDF</button>
      <button onclick="history.back()">Volver</button></div></div>
    <section class="tarjeta tabla-wrap">${htmlCuenta(u)}</section>`;
};

function htmlCuenta(u) {
  return `<h3>${esc(u.consorcio)} · ${esc(u.nombre)} ${esc([u.piso, u.depto].filter(Boolean).join(' '))}</h3>
    <table><caption class="sr">Movimientos</caption><thead><tr><th>Fecha</th><th>Concepto</th><th class="num">Debe</th><th class="num">Haber</th><th class="num">Saldo</th></tr></thead><tbody>
    ${u.movimientos.map(m => `<tr><td>${fecha(m.fecha)}</td><td>${esc(m.concepto)}</td><td class="num">${m.debe ? plata(m.debe) : ''}</td><td class="num">${m.haber ? plata(m.haber) : ''}</td><td class="num">${plata(m.saldo)}</td></tr>`).join('') || '<tr><td colspan="5" class="sutil">Sin movimientos.</td></tr>'}
    </tbody><tfoot><tr><th colspan="4">Saldo actual</th><th class="num">${plata(u.saldo)}</th></tr></tfoot></table>`;
}

// ── ADMINISTRACIÓN (datos del encabezado de las expensas) y RUBROS ──
VISTAS.administracion = async () => {
  const [a, rubros, act] = await Promise.all([api('/api/administracion'), api('/api/rubros'), api('/api/actualizacion')]);
  S.admin = a; S.rubros = rubros;
  $('#vista').innerHTML = `
    <div class="encabezado"><h2>Administración</h2></div>
    <section class="tarjeta"><div class="encabezado"><h3>Datos de la administración</h3>
      <div class="botones"><button class="primario" onclick="modalAdministracion()">Editar</button></div></div>
      <p class="sutil">Salen en el encabezado de todas las expensas impresas.</p>
      <dl class="datos dos-columnas">
        <dt>Nombre</dt><dd>${esc(a.nombre) || '<span class="chip rojo">falta cargarlo</span>'}</dd><dt>Domicilio</dt><dd>${esc(a.domicilio) || '—'}</dd>
        <dt>Horarios</dt><dd>${esc(a.horarios) || '—'}</dd><dt>CUIT</dt><dd>${esc(a.cuit) || '—'}</dd>
        <dt>Teléfono</dt><dd>${esc(a.telefono) || '—'}</dd><dt>Email</dt><dd>${esc(a.email) || '—'}</dd>
        <dt>Inscripción R.P.A.</dt><dd>${esc(a.inscripcion_rpa) || '—'}</dd><dt>Situación fiscal</dt><dd>${esc(a.situacion_fiscal) || '—'}</dd>
      </dl></section>
    <section class="tarjeta"><div class="encabezado"><h3>Rubros de gastos</h3>
      <div class="botones"><button class="primario" onclick="modalRubro()">Nuevo rubro</button></div></div>
      <p class="sutil">Agrupan los gastos en las expensas impresas, numerados como pide la Ley 941. El 1 es el de sueldos del personal.</p>
      <div class="tabla-wrap"><table><caption class="sr">Rubros</caption><thead><tr><th>Número</th><th>Nombre</th><th></th></tr></thead><tbody>
      ${rubros.map(r => `<tr class="${r.activo ? '' : 'baja'}"><td>${r.numero}</td><td>${esc(r.nombre)}</td>
        <td class="botones"><button class="chico" onclick="modalRubro(${r.id})">Editar</button>
        <button class="chico ${r.activo ? 'peligro' : ''}" onclick="hacer(api('/api/rubros/${r.id}/${r.activo ? 'baja' : 'alta'}', {metodo:'POST'}), null, 'administracion')">${r.activo ? 'Dar de baja' : 'Reactivar'}</button></td></tr>`).join('')}
      </tbody></table></div></section>
    ${htmlVersion(act)}`;
};

function modalAdministracion() {
  const a = S.admin;
  formModal('Datos de la administración',
    campo('Nombre', 'nombre', a.nombre, 'required') + campo('Domicilio', 'domicilio', a.domicilio) + campo('Horarios de atención', 'horarios', a.horarios) +
    campo('CUIT', 'cuit', a.cuit) + campo('Teléfono', 'telefono', a.telefono, 'type="tel"') + campo('Email', 'email', a.email, 'type="email"') +
    campo('Inscripción R.P.A.', 'inscripcion_rpa', a.inscripcion_rpa) + campo('Situación fiscal', 'situacion_fiscal', a.situacion_fiscal, 'placeholder="ej. Monotributo, Responsable inscripto"'),
    async d => { await api('/api/administracion', { metodo: 'PUT', datos: d }); cerrarModal(); avisar('Datos guardados.'); irA('administracion'); });
}

function modalRubro(id) {
  const r = id ? S.rubros.find(x => x.id === id) : { numero: Math.max(0, ...S.rubros.map(x => x.numero)) + 1 };
  formModal(id ? 'Editar rubro' : 'Nuevo rubro', campo('Número', 'numero', r.numero, 'required inputmode="numeric"') + campo('Nombre', 'nombre', r.nombre, 'required'),
    async d => { await api(id ? '/api/rubros/' + id : '/api/rubros', { metodo: id ? 'PUT' : 'POST', datos: d }); cerrarModal(); avisar('Rubro guardado.'); irA('administracion'); });
}

// ── USUARIOS (solo administradores) ──
VISTAS.usuarios = async () => {
  if (!S.usuario.es_admin) return irA('inicio');
  const lista = await api('/api/usuarios');
  S.usuarios = lista;
  $('#vista').innerHTML = `
    <div class="encabezado"><h2>Usuarios</h2><div class="botones"><button class="primario" onclick="modalUsuario()">Nuevo usuario</button></div></div>
    <p class="sutil">Quiénes entran al sistema. Un administrador además maneja los usuarios. Siempre tiene que quedar al menos un administrador activo.</p>
    <div class="tarjeta tabla-wrap"><table><caption class="sr">Usuarios</caption><thead><tr><th>Usuario</th><th>Nombre</th><th>Rol</th><th>Estado</th><th></th></tr></thead><tbody>
      ${lista.map(u => `<tr class="${u.activo ? '' : 'baja'}"><td><b>${esc(u.usuario)}</b></td><td>${esc(u.nombre)}${u.id === S.usuario.id ? ' <span class="sutil">(vos)</span>' : ''}</td>
        <td>${u.es_admin ? 'Administrador' : 'Usuario'}</td>
        <td>${u.activo ? (u.debe_cambiar ? 'Contraseña provisoria' : 'Activo') : 'De baja'}</td>
        <td class="botones"><button class="chico" onclick="modalUsuario(${u.id})">Editar</button>
          ${u.id !== S.usuario.id ? `<button class="chico" onclick="modalRestablecer(${u.id})">Restablecer contraseña</button>
          <button class="chico ${u.activo ? 'peligro' : ''}" onclick="hacer(api('/api/usuarios/${u.id}/${u.activo ? 'baja' : 'alta'}', {metodo:'POST'}), null, 'usuarios')">${u.activo ? 'Dar de baja' : 'Reactivar'}</button>` : ''}</td></tr>`).join('')}
    </tbody></table></div>`;
};

function modalUsuario(id) {
  const u = id ? S.usuarios.find(x => x.id === id) : null;
  formModal(u ? 'Editar ' + esc(u.nombre) : 'Nuevo usuario',
    (u ? '' : campo('Usuario (para entrar, sin espacios)', 'usuario', '', 'required autocapitalize="none"')) + campo('Nombre', 'nombre', u?.nombre, 'required') +
    (u ? '' : campo('Contraseña provisoria (mínimo 6; la cambia al entrar)', 'password', '', 'required autocomplete="off"')) +
    `<label class="check ancho"><input type="checkbox" name="es_admin" ${u?.es_admin ? 'checked' : ''}> Administrador (maneja usuarios)</label>`,
    async d => {
      await api(u ? '/api/usuarios/' + id : '/api/usuarios', { metodo: u ? 'PUT' : 'POST', datos: d });
      cerrarModal(); avisar(u ? 'Usuario actualizado.' : 'Usuario creado: entra con la contraseña provisoria.');
      if (u && id === S.usuario.id) return entrar();
      irA('usuarios');
    });
}

function modalRestablecer(id) {
  const u = S.usuarios.find(x => x.id === id);
  formModal('Restablecer contraseña de ' + esc(u.nombre), campo('Contraseña provisoria (mínimo 6)', 'password', '', 'required autocomplete="off" class="ancho"'),
    async d => { await api(`/api/usuarios/${id}/password`, { metodo: 'POST', datos: d }); cerrarModal(); avisar('Contraseña restablecida.'); irA('usuarios'); },
    { boton: 'Restablecer' });
}

// ── arranque ──
S.token = leer('edif_token');
if (S.token) entrar(); else mostrarLogin();
