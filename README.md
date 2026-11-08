# Noticiario CIFP La Granja

Noticiario que se actualiza solo con noticias sobre el CIFP La Granja y sobre agricultura, ganadería, forestal, medio ambiente, jardinería, industrias alimentarias, maquinaria y FP agraria en Cantabria y España.

- Web: https://manuelhacs.github.io/cifp_noticias/
- RSS para suscribirse: https://manuelhacs.github.io/cifp_noticias/feed.xml

## Áreas (según la oferta del centro)

| Área | Ciclos relacionados |
|---|---|
| Agricultura y agroecología | FPB Actividades Agropecuarias · GM Producción Agropecuaria · GM Producción Agroecológica |
| Ganadería y sanidad animal | GS Ganadería y Asistencia en Sanidad Animal |
| Actividades ecuestres | GM Actividades Ecuestres |
| Jardinería, floristería y paisajismo | FPB Agrojardinería y Composiciones Florales · GM Jardinería y Floristería · GS Paisajismo y Medio Rural |
| Forestal y medio natural | GS Gestión Forestal y del Medio Natural |
| Industrias alimentarias (lácteos) | GM Elaboración de Productos Alimenticios |
| Electromecánica de maquinaria | GM Electromecánica de Maquinaria (agroforestal e industrial) |
| Química y salud ambiental | GS Química y Salud Ambiental · GM Sanidad Ambiental Aplicada |
| El centro y la FP | Noticias del propio CIFP (incluido el RSS de cifplagranja.com) |

## Cómo funciona

1. Cada 3 horas (de 7:00 a 22:00, aprox.) GitHub Actions ejecuta `scripts/actualizar_noticias.py`.
2. El script consulta las búsquedas de Google Noticias y los feeds RSS de `config.json`, descarta lo antiguo o irrelevante, clasifica cada noticia por **área** y **ámbito** (CIFP / Cantabria / Nacional) y quita duplicados.
3. Guarda el resultado en `news.json` (lo lee la web) y `feed.xml` (RSS), y los sube al repositorio.
4. GitHub Pages publica la web.

## Puesta en marcha (una sola vez)

1. **Settings → Pages**: *Source* = "Deploy from a branch", rama `main`, carpeta `/ (root)`.
2. **Settings → Actions → General → Workflow permissions**: marcar "Read and write permissions".
3. **Actions → Actualizar noticias → Run workflow** para generar las primeras noticias sin esperar.

## Ajustes habituales (editando `config.json` desde GitHub)

| Quiero… | Cambia… |
|---|---|
| Añadir un tema o una búsqueda | Una línea más en `busquedas` |
| Añadir un periódico o revista con RSS | Una línea en `feeds` |
| Que algo se clasifique mejor | Las `palabras` del área correspondiente |
| Ocultar un tipo de noticia | Añadir la palabra a `excluir` |
| Guardar más o menos tiempo | `dias_maximos` (general) y `dias_maximos_cifp` |

Al guardar `config.json` el noticiario se regenera automáticamente.

## Notas

- Si una fuente falla, se ignora y se sigue con el resto (se ve en el registro de *Actions*).
- GitHub pausa las tareas programadas de repositorios sin actividad durante 60 días; si ocurre, basta con pulsar *Enable workflow* en la pestaña *Actions*.
- Los enlaces de Google Noticias redirigen a la noticia original. El feed de Google Noticias está pensado para uso personal y no comercial.
