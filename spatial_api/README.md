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
- associating buildings with cadastral lots;
- calculating building-to-lot overlap;
- assigning cadastral use information to buildings;
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
  | WFS
  v
GeoSampa
```

The Main API receives requests from the client and forwards the spatial processing request to this service.

The Spatial API then communicates with GeoSampa, performs the geospatial processing, and returns the result to the Main API.

---

## Spatial API

The Spatial API is implemented using FastAPI.

Responsibilities:

- receive spatial analysis requests from the Main API;
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

GeoSampa is the geographic information platform of the Municipality of São Paulo.

The WFS endpoint used by the application is:

```text
https://wfs.geosampa.prefeitura.sp.gov.br/geoserver/geoportal/wfs
```

The application uses the WFS operation:

```text
GetFeature
```

with GeoJSON output:

```text
outputFormat=application/json
```

Requests are restricted spatially using a bounding box generated from the user's area of interest.

No authentication is required for the WFS requests used by this application.

---

## GeoSampa layers

Two GeoSampa layers are used.

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

These attributes are renamed internally as:

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

This layer provides cadastral fiscal lot geometries and attributes.

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

These attributes are used to obtain:

- lot identifier;
- cadastral property use;
- address;
- street number;
- lot area;
- built area;
- cadastral status.

Only cadastral lots where:

```text
tx_situ_lote = ATIVO
```

are considered during the building-to-lot association.

Inactive or cancelled lots are excluded from the matching process.

---

## Building-to-lot matching methodology

The building and cadastral lot datasets are spatially associated.

The workflow is:

```text
Building footprint
        |
        v
Find intersecting ACTIVE cadastral lots
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
Assign cadastral information to building
```

If a building intersects more than one active cadastral lot, the lot with the largest spatial overlap is selected.

The overlap ratio is calculated as:

```text
overlap ratio = intersection area / building geometry area
```

The result is constrained between:

```text
0 and 1
```

---

## Match quality

Each building-to-lot association receives a match-quality classification based on the overlap ratio.

| Overlap ratio | Match quality |
|---|---|
| >= 0.90 | very_high |
| >= 0.75 | high |
| >= 0.50 | medium |
| < 0.50 | low |
| no active lot | unmatched |

This allows API consumers to identify associations that may require further inspection.

---

## Use classification

The property-use classification comes from the cadastral lot associated with each building.

If a building is successfully associated with an active lot, the value from:

```text
dc_tipo_uso_imovel
```

is returned.

Examples may include:

```text
Residencial
Não residencial
Terreno
```

Special values are used when classification cannot be assigned.

### No active lot match

```text
NO_LOT_MATCH
```

This means the building did not intersect an active cadastral lot.

### Active lot without use information

```text
LOT_WITHOUT_USE
```

This means an active lot was matched, but its cadastral use attribute was empty.

---

## Coordinate Reference Systems

The API uses three CRS stages.

### Input

Input GeoJSON geometries are expected in:

```text
EPSG:4326
```

WGS 84 geographic coordinates.

### Spatial processing

Spatial operations are performed using:

```text
EPSG:31983
```

This projected CRS allows areas and spatial overlaps to be calculated in metres.

### Output

GeoJSON output is converted back to:

```text
EPSG:4326
```

---

# API Routes

The Spatial API exposes five routes.

---

## GET `/`

Returns basic information about the API.

Example:

```bash
curl http://localhost:8001/
```

Example response:

```json
{
  "name": "GeoSampa Spatial API",
  "version": "0.3.0",
  "status": "running",
  "results_directory": "/app/results",
  "save_results": true
}
```

---

## GET `/health`

Checks the status of the Spatial API and its connection to GeoSampa.

Example:

```bash
curl http://localhost:8001/health
```

Example response:

```json
{
  "status": "ok",
  "geosampa": "ok",
  "results_directory": "/app/results"
}
```

---

## GET `/layers`

Returns information about the external GeoSampa service, the layers used by the application, and the coordinate reference systems.

Example:

```bash
curl http://localhost:8001/layers
```

Example response:

```json
{
  "external_service": {
    "name": "GeoSampa",
    "protocol": "WFS 2.0.0",
    "endpoint": "https://wfs.geosampa.prefeitura.sp.gov.br/geoserver/geoportal/wfs",
    "authentication": "none"
  },
  "layers": {
    "buildings": {
      "type_name": "geoportal:edificacao",
      "description": "Building footprint polygons from GeoSampa."
    },
    "lots": {
      "type_name": "geoportal:lote_cidadao",
      "description": "Cadastral lot polygons used to obtain property use classification."
    }
  },
  "crs": {
    "input": "EPSG:4326",
    "processing": "EPSG:31983",
    "output": "EPSG:4326"
  }
}
```

---

## POST `/validate-boundary`

Validates a Polygon or MultiPolygon without performing the complete GeoSampa analysis.

The route verifies:

- geometry type;
- geometry validity;
- empty geometry;
- geographic bounds;
- projected bounds;
- area in square metres;
- area in hectares.

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

Example response:

```json
{
  "valid": true,
  "geometry_type": "Polygon",
  "is_empty": false,
  "input_crs": "EPSG:4326",
  "processing_crs": "EPSG:31983",
  "bounds_wgs84": {
    "xmin": -46.66,
    "ymin": -23.56,
    "xmax": -46.655,
    "ymax": -23.555
  },
  "area_m2": 282000,
  "area_hectares": 28.2
}
```

The exact area depends on the submitted geometry.

---

## POST `/buildings`

Executes the complete geospatial analysis.

The route:

1. validates the input boundary;
2. converts the boundary to EPSG:31983;
3. creates a bounding box;
4. requests building footprints from GeoSampa;
5. requests cadastral lots from GeoSampa;
6. filters features using the exact user-defined area;
7. keeps only active cadastral lots;
8. calculates building-to-lot intersections;
9. selects the active lot with the largest overlap for each building;
10. calculates overlap ratios;
11. classifies match quality;
12. assigns cadastral use information;
13. generates analysis statistics;
14. converts the results to EPSG:4326;
15. saves result files;
16. returns a GeoJSON FeatureCollection.

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

Each returned building may contain attributes such as:

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

The original building footprint geometry is returned rather than the geometry clipped to the area of interest.

---

## Generated files

When result saving is enabled, files are stored in:

```text
/app/results
```

Inside Docker.

When used with the GeoBuilding SP Docker Compose configuration, this directory is mounted to:

```text
./results
```

on the host machine.

A successful analysis can generate:

```text
20260920_145752_buildings.geojson
20260920_145752_unmatched.geojson
20260920_145752_low_confidence.geojson
20260920_145752_summary.json
```

### Buildings

```text
*_buildings.geojson
```

Contains all building footprints returned by the analysis.

### Unmatched

```text
*_unmatched.geojson
```

Contains buildings that could not be associated with an active cadastral lot.

### Low confidence

```text
*_low_confidence.geojson
```

Contains matched buildings whose overlap ratio is lower than:

```text
0.50
```

### Summary

```text
*_summary.json
```

Contains aggregate statistics from the analysis.

---

# Installation

## Requirements

The recommended way to run the application is with Docker.

Required:

- Docker
- internet access to GeoSampa

---

## Repository structure

```text
geobuilding-spatial-api/
│
├── spatial_api/
│   ├── main.py
│   └── requirements.txt
│
├── results/
│
├── Dockerfile
├── .dockerignore
├── .gitignore
└── README.md
```

---

## Python dependencies

The application uses:

```text
fastapi
uvicorn[standard]
requests
pandas
geopandas
shapely
pyproj
```

These dependencies are listed in:

```text
spatial_api/requirements.txt
```

---

# Running with Docker

Build the Docker image:

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

The API will then be available at:

```text
http://localhost:8001
```

Swagger:

```text
http://localhost:8001/docs
```

---

# Running with Docker Compose

When used as part of the complete GeoBuilding SP application, the Spatial API is started by the Docker Compose configuration located in the Main API project.

Example:

```bash
docker compose up -d --build
```

The Main API communicates with this service internally through:

```text
http://spatial-api:8001
```

---

# Environment variables

The Spatial API supports the following environment variables.

### `RESULTS_DIR`

Directory used to save output files.

Default:

```text
/app/results
```

### `SAVE_RESULTS`

Controls whether output files are written.

Default:

```text
true
```

Example:

```bash
-e SAVE_RESULTS=true
```

---

# Testing the API

Swagger can be used to interact with all routes:

```text
http://localhost:8001/docs
```

A recommended test sequence is:

```text
GET /health
       |
       v
GET /layers
       |
       v
POST /validate-boundary
       |
       v
POST /buildings
```

This verifies:

- the API is running;
- GeoSampa is available;
- the configured layers are visible;
- the input polygon is valid;
- the complete spatial-processing workflow works correctly.

---

# Technologies

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

# Notes and limitations

The cadastral use returned for a building is not an intrinsic attribute of the building footprint.

It is obtained from the active cadastral lot spatially associated with that building.

Therefore, the `use` attribute should be interpreted as:

> cadastral use of the active fiscal lot associated with the building.

A building may:

- intersect more than one cadastral lot;
- have no active lot match;
- have a low spatial overlap with its selected lot;
- match an active lot without a use classification.

These cases are represented explicitly using:

```text
overlap_ratio
match_quality
NO_LOT_MATCH
LOT_WITHOUT_USE
```

The API also uses a bounding box to request features efficiently from GeoSampa and then applies an exact spatial intersection against the user-defined polygon.

---
