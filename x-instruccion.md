Para el segundo trabajo grupal del curso (fase2), deberá hacer una presentación (que deberá subir a Canvas) donde se evidencie el proceso ETL (Extract, Transform, Load) y cada punto solicitado en la rúbrica. Recuerde que se evaluará que el contenido esté en la presentación para poder evaluar por igual a todos:

Se debe modificar el proyecto asociado a su equipo en Gitlab UDP https://giteit.udp.cl el cual debe contener: 

0.- Imagen con el diagrama de su BD para dimensionar las capacidades que tendrá y un mejor entendimiento de ésta. Debe estar acompañada de un archivo .sql que permita crear la BD desde cero con la estructura que utilizará.

1.- Carpeta Infraestructura: Archivo que automatiza la extracción y transformación de la infraestructura (nodos y aristas) a un *json.

2.- Carpeta Metadata: N archivos, donde cada uno automatiza la extracción y transformación de una API o BD de la metadata a un *json.

3.- Carpeta Amenazas: N archivos, donde cada uno automatiza la extracción y transformación de una API o BD de la amenaza a un *json.

4.- Cada archivo json o geojson debe tener un un archivo asociado que explique la estructura del archivo y a qué corresponde cada valor del *json para facilitar su entendimiento.

6.- Por cada archivo *json, deberá generar un archivo que permita cargar esa información a su BD en base al diseño de ésta.

7.- Carpeta Sitio Web: Archivo que permita crear un sitio con leaftlet para visualizar la infraestructura, la información de la metadata y de las amenazas.

8.- El sitio deberá mostrar una ruta generada con pgr_dijkstra, utilizando la longitud de la ruta como costo, que muestre a modo de ejemplo una ruta que sea una posible solución a su problema planteado. Esta ruta será el peor caso que podría resolver su problemática, ya que no considerará la metadata ni las posibles amenazas (eso será parte de la fase3).

9.- Deberá crear un archivo main (en la carpeta raíz de su github) que permita ejecutar los procesos anteriores de forma automatizada, desde la descarga de toda la información, su importación en la bd y habilitación del sitio web.

Para asegurar que todas sus implementaciones funcionen correctamente, estas DEBEN correr en contendores DOCKER para asegurar compatibilidad de librerías y versiones de software.