# GeoBuilding SP — Spatial API

## Overview

The GeoBuilding SP Spatial API is the secondary service responsible for geospatial processing in the GeoBuilding SP architecture.

It receives a Polygon or MultiPolygon defining an area of interest, queries the City of São Paulo's GeoSampa WFS service, retrieves building footprints and cadastral lots, performs spatial matching between them, and returns enriched building geometries as GeoJSON.

The Spatial API contains the main geospatial business logic of the application.

Its responsibilities include:

- validating input geometries;
- transforming coordinate reference systems;
- querying GeoSampa WFS;
- retrieving building footprints;
- retrieving cadastral fiscal lots;
- filtering only active cadastral lots;
- performing spatial intersections;
- associating buildings with lots;
- calculating building-to-lot overlap;
- assigning cadastral use information;
- evaluating match quality;
- saving GeoJSON output files.

---

## Architecture

The Spatial API is the secondary component in the GeoBuilding SP architecture.

```text
Client
  |
  | REST
  v
Main API
  |
  | REST
  v
Spatial API
  |
  | WFS 2.0
  v
GeoSampa
```

The Main API receives requests from the client and forwards spatial-processing requests to this service.

The Spatial API communicates with GeoSampa, performs the geospatial processing, and returns the result to the Main API.

---

## Spatial API

The Spatial API is implemented using FastAPI.

Responsibilities:

- receive spatial analysis requests;
- validate GeoJSON Polygon and MultiPolygon geometries;
- convert geometries between coordinate reference systems;
- query GeoSampa WFS;
- retrieve buildings and cadastral lots;
- filter active cadastral lots;
- spatially associate buildings with lots;
- calculate overlap ratios;
- classify match quality;
- generate enriched GeoJSON outputs;
- save result files.

Default port:

```text
8001
```

Swagger:

```text
http://localhost:8001/docs
```

---

## External API — GeoSampa

The Spatial API communicates directly with the GeoSampa Web Feature Service.

WFS endpoint:

```text
https://wfs.geosampa.prefeitura.sp.gov.br/geoserver/geoportal/wfs
```

Authentication:

```text
None
```

WFS version:

```text
2.0.0
```

Operation used:

```text
GetFeature
```

Output format:

```text
application/json
```

Requests are spatially restricted using a bounding box generated from the submitted area of interest.

---

## GeoSampa layers

### Building footprints

```text
geoportal:edificacao
```

This layer provides building footprint geometries.

Relevant attributes include:

```text
cd_identificador
qt_area_projecao_beiral
qt_altura_edificacao
```

These are renamed internally as:

```text
building_id
footprint_area_m2
height_m
```

---

### Cadastral lots

```text
geoportal:lote_cidadao
```

This layer provides fiscal cadastral lot geometries and attributes.

Relevant attributes include:

```text
cd_identificador
dc_tipo_uso_imovel
nm_logradouro_completo
cd_numero_porta
qt_area_terreno
qt_area_construida
tx_situ_lote
```

Only lots where:

```text
tx_situ_lote = ATIVO
```

are considered during the building-to-lot association.

Inactive or cancelled lots are excluded.

---

## Building-to-lot matching methodology

Buildings and active cadastral lots are spatially associated.

Workflow:

```text
Building footprint
        |
        v
Find intersecting active cadastral lots
        |
        v
Calculate intersection geometry
        |
        v
Calculate overlap area
        |
        v
Calculate overlap ratio
        |
        v
Select lot with largest overlap
        |
        v
Assign cadastral information
```

If a building intersects multiple active lots, the lot with the largest spatial overlap is selected.

The overlap ratio is calculated as:

```text
overlap ratio = intersection area / building geometry area
```

The ratio is constrained between:

```text
0 and 1
```

---

## Match quality

Each association receives a quality classification based on overlap.

| Overlap ratio | Match quality |
|---|---|
| >= 0.90 | very_high |
| >= 0.75 | high |
| >= 0.50 | medium |
| < 0.50 | low |
| no active lot | unmatched |

This allows API consumers to evaluate the reliability of the building-to-lot association.

---

## Use classification

The cadastral use is obtained from:

```text
dc_tipo_uso_imovel
```

Examples may include:

```text
Residencial
Não residencial
Terreno
```

Special values are used when necessary.

### No active lot match

```text
NO_LOT_MATCH
```

### Active lot without use information

```text
LOT_WITHOUT_USE
```

---

## Coordinate Reference Systems

### Input

```text
EPSG:4326
```

### Spatial processing

```text
EPSG:31983
```

### Output

```text
EPSG:4326
```

The projected CRS is used so that areas and spatial overlaps can be calculated in square metres.

---

## API Routes

The Spatial API exposes five routes.

### GET `/`

Returns basic API information.

Example:

```bash
curl http://localhost:8001/
```

---

### GET `/health`

Checks the Spatial API and GeoSampa availability.

Example:

```bash
curl http://localhost:8001/health
```

---

### GET `/layers`

Returns information about:

- GeoSampa;
- the WFS endpoint;
- the building layer;
- the lot layer;
- the CRS configuration.

Example:

```bash
curl http://localhost:8001/layers
```

---

### POST `/validate-boundary`

Validates a Polygon or MultiPolygon without executing the full GeoSampa workflow.

Example request:

```json
{
  "boundary": {
    "type": "Polygon",
    "coordinates": [
      [
        [-46.660, -23.560],
        [-46.655, -23.560],
        [-46.655, -23.555],
        [-46.660, -23.555],
        [-46.660, -23.560]
      ]
    ]
  }
}
```

The route returns information such as:

- geometry type;
- validity;
- geographic bounds;
- projected bounds;
- area in square metres;
- area in hectares.

---

### POST `/buildings`

Executes the complete spatial analysis.

Workflow:

1. validate the boundary;
2. convert it to EPSG:31983;
3. generate a bounding box;
4. retrieve buildings from GeoSampa;
5. retrieve cadastral lots;
6. apply an exact intersection with the AOI;
7. keep only active lots;
8. calculate building-to-lot intersections;
9. select the active lot with the largest overlap;
10. calculate overlap ratios;
11. classify match quality;
12. assign cadastral use information;
13. generate summary statistics;
14. convert results to EPSG:4326;
15. save result files;
16. return a GeoJSON FeatureCollection.

Example request:

```json
{
  "boundary": {
    "type": "Polygon",
    "coordinates": [
      [
        [-46.660, -23.560],
        [-46.655, -23.560],
        [-46.655, -23.555],
        [-46.660, -23.555],
        [-46.660, -23.560]
      ]
    ]
  }
}
```

---

## Output structure

The response contains:

```text
request_id
summary
files
type
features
```

Example:

```json
{
  "request_id": "20260920_145752",
  "summary": {
    "total_buildings": 533,
    "matched_to_active_lot": 418,
    "without_active_lot_match": 115,
    "match_percentage": 78.42
  },
  "files": {
    "buildings": "20260920_145752_buildings.geojson",
    "unmatched": "20260920_145752_unmatched.geojson",
    "low_confidence": "20260920_145752_low_confidence.geojson",
    "summary": "20260920_145752_summary.json"
  },
  "type": "FeatureCollection",
  "features": []
}
```

---

## Building output attributes

Returned buildings may contain:

```text
building_id
footprint_area_m2
height_m
lot_id
use
address
number
lot_area_m2
built_area_m2
lot_status
overlap_area_m2
overlap_ratio
has_lot_match
use_classification
match_quality
```

The original building footprint geometry is returned rather than a geometry clipped to the submitted area.

---

## Generated files

Generated files are stored inside Docker at:

```text
/app/results
```

When run using the complete project setup, this directory is mounted to a host `results/` directory.

A successful analysis may generate:

```text
20260920_145752_buildings.geojson
20260920_145752_unmatched.geojson
20260920_145752_low_confidence.geojson
20260920_145752_summary.json
```

---

## Installation

### Requirements

- Docker
- internet access to GeoSampa

---

## Repository structure

```text
geobuilding-spatial-api/
├── README.md
├── Dockerfile
├── .dockerignore
├── .gitignore
├── spatial_api/
│   ├── main.py
│   └── requirements.txt
├── tests/
│   └── test_spatial_api.py
└── results/
```

---

## Running with Docker

Build the image:

```bash
docker build -t geobuilding-spatial-api .
```

Run the container:

```bash
docker run \
  --name geobuilding-spatial-api \
  -p 8001:8001 \
  -e RESULTS_DIR=/app/results \
  -e SAVE_RESULTS=true \
  -v "$(pwd)/results:/app/results" \
  geobuilding-spatial-api
```

Swagger:

```text
http://localhost:8001/docs
```

---

## Running with Docker Compose

When used with the complete GeoBuilding SP application, the Spatial API is started from the `docker-compose.yml` file in the Main API repository.

The Main API communicates with the Spatial API internally through:

```text
http://spatial-api:8001
```

---

## Environment variables

### `RESULTS_DIR`

Output directory.

Default:

```text
/app/results
```

### `SAVE_RESULTS`

Controls whether generated files are written.

Default:

```text
true
```

---

## Tests

Quick smoke tests are included.

Tests verify:

- root endpoint;
- `/layers`;
- valid Polygon handling;
- rejection of invalid geometry types.

The tests do not call GeoSampa directly, which keeps them fast and avoids failures caused by external-service availability.

Create a virtual environment:

```bash
python3 -m venv .venv
source .venv/bin/activate
```

Install dependencies:

```bash
python -m pip install -r spatial_api/requirements.txt
```

Run:

```bash
python -m pytest -q
```

---

## Technologies

- Python 3.11
- FastAPI
- GeoPandas
- Shapely
- pandas
- PyProj
- Requests
- GeoJSON
- Docker
- GeoSampa WFS

---

## Notes and limitations

The returned property-use classification is derived from the active cadastral lot spatially associated with the building.

It should therefore be interpreted as:

> cadastral use of the active fiscal lot associated with the building.

A building may:

- intersect multiple lots;
- have no active lot match;
- have a low overlap ratio;
- match a lot without a use classification.

These situations are explicitly represented using:

```text
overlap_ratio
match_quality
NO_LOT_MATCH
LOT_WITHOUT_USE
```

The API uses a bounding box to retrieve GeoSampa features efficiently and then applies an exact spatial intersection against the submitted boundary.

---

## Data source and attribution

This API consumes GeoSampa data produced by the Municipality of São Paulo.

GeoSampa should be credited as the source of the geospatial data used by the application.

---

## Author

MVP developed for a software componentization and web-services assignment.
