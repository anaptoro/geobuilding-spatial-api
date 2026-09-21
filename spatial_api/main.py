import os
import json
from pathlib import Path
from datetime import datetime

import requests
import pandas as pd
import geopandas as gpd

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from shapely.geometry import shape, mapping


# =========================================================
# CONFIGURATION
# =========================================================

WFS_URL = (
    "https://wfs.geosampa.prefeitura.sp.gov.br/"
    "geoserver/geoportal/wfs"
)

BUILDING_LAYER = "geoportal:edificacao"
LOT_LAYER = "geoportal:lote_cidadao"

INPUT_CRS = "EPSG:4326"
GEOSAMPA_CRS = "EPSG:31983"

RESULTS_DIR = Path(
    os.getenv(
        "RESULTS_DIR",
        "/app/results",
    )
)

SAVE_RESULTS = (
    os.getenv(
        "SAVE_RESULTS",
        "true",
    ).lower()
    == "true"
)

RESULTS_DIR.mkdir(
    parents=True,
    exist_ok=True,
)


# =========================================================
# FASTAPI APP
# =========================================================

app = FastAPI(
    title="GeoSampa Spatial API",
    description=(
        "Secondary API responsible for spatial processing "
        "of GeoSampa building footprints and cadastral lots."
    ),
    version="0.3.0",
)


# =========================================================
# REQUEST MODEL
# =========================================================

class AnalysisRequest(BaseModel):
    boundary: dict


# =========================================================
# WFS FUNCTION
# =========================================================

def fetch_wfs_layer(
    type_name: str,
    bbox_31983: tuple,
) -> dict:

    xmin, ymin, xmax, ymax = bbox_31983

    params = {
        "service": "WFS",
        "version": "2.0.0",
        "request": "GetFeature",
        "typeNames": type_name,
        "outputFormat": "application/json",
        "srsName": GEOSAMPA_CRS,
        "bbox": (
            f"{xmin},{ymin},{xmax},{ymax},"
            f"{GEOSAMPA_CRS}"
        ),
    }

    try:

        response = requests.get(
            WFS_URL,
            params=params,
            timeout=60,
        )

        response.raise_for_status()

    except requests.RequestException as exc:

        raise HTTPException(
            status_code=502,
            detail=(
                f"GeoSampa WFS request failed "
                f"for {type_name}: {exc}"
            ),
        )

    try:

        return response.json()

    except ValueError:

        raise HTTPException(
            status_code=502,
            detail=(
                f"GeoSampa returned invalid JSON "
                f"for {type_name}."
            ),
        )


# =========================================================
# MATCH QUALITY
# =========================================================

def classify_match_quality(
    ratio,
):

    if pd.isna(ratio):
        return "unmatched"

    if ratio >= 0.90:
        return "very_high"

    if ratio >= 0.75:
        return "high"

    if ratio >= 0.50:
        return "medium"

    return "low"


# =========================================================
# USE CLASSIFICATION
# =========================================================

def classify_use_status(
    row,
):

    if pd.isna(
        row["lot_id"]
    ):
        return "NO_LOT_MATCH"

    if pd.isna(
        row["use"]
    ):
        return "LOT_WITHOUT_USE"

    return row["use"]


# =========================================================
# GEODATAFRAME -> GEOJSON FEATURES
# =========================================================

def geodataframe_to_features(
    gdf: gpd.GeoDataFrame,
):

    features = []

    for _, row in gdf.iterrows():

        properties = {}

        for column in gdf.columns:

            if column == "geometry":
                continue

            value = row[column]

            if pd.isna(value):
                value = None

            elif hasattr(
                value,
                "item",
            ):
                value = value.item()

            properties[
                column
            ] = value

        features.append(
            {
                "type": "Feature",

                "geometry":
                    mapping(
                        row.geometry
                    ),

                "properties":
                    properties,
            }
        )

    return features


# =========================================================
# SAVE GEOJSON
# =========================================================

def save_geojson(
    gdf: gpd.GeoDataFrame,
    filepath: Path,
):

    if len(gdf) == 0:
        return

    gdf.to_file(
        filepath,
        driver="GeoJSON",
    )


# =========================================================
# BOUNDARY VALIDATION HELPER
# =========================================================

def validate_boundary_geometry(
    boundary: dict,
):

    try:

        geometry = shape(
            boundary
        )

    except Exception as exc:

        raise HTTPException(
            status_code=400,
            detail=(
                f"Invalid GeoJSON geometry: {exc}"
            ),
        )

    if geometry.geom_type not in [
        "Polygon",
        "MultiPolygon",
    ]:

        raise HTTPException(
            status_code=400,
            detail=(
                "Boundary must be a "
                "Polygon or MultiPolygon."
            ),
        )

    if geometry.is_empty:

        raise HTTPException(
            status_code=400,
            detail=(
                "Boundary cannot be empty."
            ),
        )

    return geometry


# =========================================================
# ROOT ENDPOINT
# =========================================================

@app.get("/")
def root():

    return {
        "name":
            "GeoSampa Spatial API",

        "version":
            "0.3.0",

        "status":
            "running",

        "results_directory":
            str(
                RESULTS_DIR
            ),

        "save_results":
            SAVE_RESULTS,
    }


# =========================================================
# HEALTH ENDPOINT
# =========================================================

@app.get("/health")
def health():

    geosampa_status = (
        "unknown"
    )

    try:

        response = requests.get(
            WFS_URL,
            params={
                "service":
                    "WFS",

                "request":
                    "GetCapabilities",

                "version":
                    "2.0.0",
            },
            timeout=10,
        )

        if (
            response.status_code
            == 200
        ):

            geosampa_status = (
                "ok"
            )

        else:

            geosampa_status = (
                f"error_"
                f"{response.status_code}"
            )

    except requests.RequestException:

        geosampa_status = (
            "unavailable"
        )


    return {
        "status":
            "ok",

        "geosampa":
            geosampa_status,

        "results_directory":
            str(
                RESULTS_DIR
            ),
    }


# =========================================================
# GET /layers
# =========================================================
#
# Documents which GeoSampa datasets are used.
# =========================================================

@app.get("/layers")
def get_layers():

    return {
        "external_service": {
            "name":
                "GeoSampa",

            "protocol":
                "WFS 2.0.0",

            "endpoint":
                WFS_URL,

            "authentication":
                "none",
        },

        "layers": {
            "buildings": {
                "type_name":
                    BUILDING_LAYER,

                "description":
                    (
                        "Building footprint "
                        "polygons from GeoSampa."
                    ),
            },

            "lots": {
                "type_name":
                    LOT_LAYER,

                "description":
                    (
                        "Cadastral lot polygons "
                        "used to obtain property "
                        "use classification."
                    ),
            },
        },

        "crs": {
            "input":
                INPUT_CRS,

            "processing":
                GEOSAMPA_CRS,

            "output":
                INPUT_CRS,
        },
    }


# =========================================================
# POST /validate-boundary
# =========================================================
#
# Validates a Polygon/MultiPolygon without querying GeoSampa.
# =========================================================

@app.post("/validate-boundary")
def validate_boundary(
    request: AnalysisRequest,
):

    geometry = (
        validate_boundary_geometry(
            request.boundary
        )
    )


    # -----------------------------------------------------
    # Input AOI
    # -----------------------------------------------------

    aoi = gpd.GeoDataFrame(
        [
            {
                "geometry":
                    geometry
            }
        ],
        crs=INPUT_CRS,
    )


    # -----------------------------------------------------
    # Project to GeoSampa CRS for area calculation
    # -----------------------------------------------------

    aoi_31983 = (
        aoi.to_crs(
            GEOSAMPA_CRS
        )
    )


    projected_geometry = (
        aoi_31983
        .geometry
        .iloc[0]
    )


    # -----------------------------------------------------
    # Geometry information
    # -----------------------------------------------------

    xmin, ymin, xmax, ymax = (
        geometry.bounds
    )

    pxmin, pymin, pxmax, pymax = (
        projected_geometry.bounds
    )


    return {
        "valid":
            bool(
                geometry.is_valid
            ),

        "geometry_type":
            geometry.geom_type,

        "is_empty":
            bool(
                geometry.is_empty
            ),

        "input_crs":
            INPUT_CRS,

        "processing_crs":
            GEOSAMPA_CRS,

        "bounds_wgs84": {
            "xmin":
                xmin,

            "ymin":
                ymin,

            "xmax":
                xmax,

            "ymax":
                ymax,
        },

        "bounds_processing_crs": {
            "xmin":
                pxmin,

            "ymin":
                pymin,

            "xmax":
                pxmax,

            "ymax":
                pymax,
        },

        "area_m2":
            round(
                projected_geometry.area,
                2,
            ),

        "area_hectares":
            round(
                projected_geometry.area
                / 10000,
                4,
            ),
    }


# =========================================================
# POST /buildings
# =========================================================

@app.post("/buildings")
def get_buildings(
    request: AnalysisRequest,
):

    # -----------------------------------------------------
    # Timestamp ID
    # -----------------------------------------------------

    request_id = (
        datetime.now()
        .strftime(
            "%Y%m%d_%H%M%S"
        )
    )


    # =====================================================
    # 1. VALIDATE INPUT
    # =====================================================

    boundary_geometry = (
        validate_boundary_geometry(
            request.boundary
        )
    )


    # =====================================================
    # 2. CREATE AOI
    # =====================================================

    aoi = gpd.GeoDataFrame(
        [
            {
                "geometry":
                    boundary_geometry
            }
        ],
        crs=INPUT_CRS,
    )


    # =====================================================
    # 3. REPROJECT AOI
    # =====================================================

    aoi_31983 = (
        aoi.to_crs(
            GEOSAMPA_CRS
        )
    )

    aoi_geom_31983 = (
        aoi_31983
        .geometry
        .iloc[0]
    )

    bbox_31983 = (
        aoi_geom_31983.bounds
    )


    # =====================================================
    # 4. FETCH BUILDINGS
    # =====================================================

    buildings_json = fetch_wfs_layer(
        BUILDING_LAYER,
        bbox_31983,
    )

    building_features = (
        buildings_json.get(
            "features",
            [],
        )
    )


    # =====================================================
    # 5. NO BUILDINGS
    # =====================================================

    if len(
        building_features
    ) == 0:

        return {
            "request_id":
                request_id,

            "summary": {
                "request_id":
                    request_id,

                "total_buildings":
                    0,

                "matched_to_active_lot":
                    0,

                "without_active_lot_match":
                    0,

                "match_percentage":
                    0,

                "by_use":
                    {},

                "by_match_quality":
                    {},
            },

            "files":
                {},

            "type":
                "FeatureCollection",

            "features":
                [],
        }


    buildings = (
        gpd.GeoDataFrame
        .from_features(
            building_features,
            crs=GEOSAMPA_CRS,
        )
    )


    # =====================================================
    # 6. FETCH LOTS
    # =====================================================

    lots_json = fetch_wfs_layer(
        LOT_LAYER,
        bbox_31983,
    )

    lot_features = (
        lots_json.get(
            "features",
            [],
        )
    )

    if len(
        lot_features
    ) > 0:

        lots = (
            gpd.GeoDataFrame
            .from_features(
                lot_features,
                crs=GEOSAMPA_CRS,
            )
        )

    else:

        lots = (
            gpd.GeoDataFrame(
                geometry=[],
                crs=GEOSAMPA_CRS,
            )
        )


    # =====================================================
    # 7. PRECISE AOI FILTER
    # =====================================================

    buildings = buildings[
        buildings
        .geometry
        .intersects(
            aoi_geom_31983
        )
    ].copy()


    if len(
        lots
    ) > 0:

        lots = lots[
            lots
            .geometry
            .intersects(
                aoi_geom_31983
            )
        ].copy()


    # =====================================================
    # 8. KEEP ACTIVE LOTS ONLY
    # =====================================================

    if (
        len(lots) > 0
        and
        "tx_situ_lote"
        in lots.columns
    ):

        lots = lots[
            lots[
                "tx_situ_lote"
            ]
            .fillna("")
            .str.upper()
            .eq("ATIVO")
        ].copy()


    # =====================================================
    # 9. BUILDING COLUMNS
    # =====================================================

    building_cols = [
        "cd_identificador",
        "qt_area_projecao_beiral",
        "qt_altura_edificacao",
        "geometry",
    ]

    building_cols = [
        col
        for col in building_cols
        if col in buildings.columns
    ]

    buildings = (
        buildings[
            building_cols
        ]
        .copy()
    )


    # =====================================================
    # 10. RENAME BUILDINGS
    # =====================================================

    buildings = buildings.rename(
        columns={
            "cd_identificador":
                "building_id",

            "qt_area_projecao_beiral":
                "footprint_area_m2",

            "qt_altura_edificacao":
                "height_m",
        }
    )


    # =====================================================
    # 11. FIX BUILDING GEOMETRY
    # =====================================================

    buildings[
        "geometry"
    ] = (
        buildings
        .geometry
        .make_valid()
    )

    buildings[
        "geometry_area_m2"
    ] = (
        buildings.geometry.area
    )


    # =====================================================
    # 12. NO ACTIVE LOTS
    # =====================================================

    if len(
        lots
    ) == 0:

        buildings[
            "lot_id"
        ] = None

        buildings[
            "use"
        ] = None

        buildings[
            "address"
        ] = None

        buildings[
            "number"
        ] = None

        buildings[
            "lot_area_m2"
        ] = None

        buildings[
            "built_area_m2"
        ] = None

        buildings[
            "lot_status"
        ] = None

        buildings[
            "overlap_area_m2"
        ] = None

        buildings[
            "overlap_ratio"
        ] = None

        result = (
            buildings.copy()
        )

    else:

        # =================================================
        # 13. LOT COLUMNS
        # =================================================

        lot_cols = [
            "cd_identificador",
            "dc_tipo_uso_imovel",
            "nm_logradouro_completo",
            "cd_numero_porta",
            "qt_area_terreno",
            "qt_area_construida",
            "tx_situ_lote",
            "geometry",
        ]

        lot_cols = [
            col
            for col in lot_cols
            if col in lots.columns
        ]

        lots = (
            lots[
                lot_cols
            ]
            .copy()
        )


        # =================================================
        # 14. RENAME LOTS
        # =================================================

        lots = lots.rename(
            columns={
                "cd_identificador":
                    "lot_id",

                "dc_tipo_uso_imovel":
                    "use",

                "nm_logradouro_completo":
                    "address",

                "cd_numero_porta":
                    "number",

                "qt_area_terreno":
                    "lot_area_m2",

                "qt_area_construida":
                    "built_area_m2",

                "tx_situ_lote":
                    "lot_status",
            }
        )


        # =================================================
        # 15. FIX LOT GEOMETRIES
        # =================================================

        lots[
            "geometry"
        ] = (
            lots
            .geometry
            .make_valid()
        )


        # =================================================
        # 16. INTERSECTIONS
        # =================================================

        intersections = (
            gpd.overlay(
                buildings,
                lots,
                how="intersection",
                keep_geom_type=False,
            )
        )


        # =================================================
        # 17. NO INTERSECTIONS
        # =================================================

        if len(
            intersections
        ) == 0:

            buildings[
                "lot_id"
            ] = None

            buildings[
                "use"
            ] = None

            buildings[
                "address"
            ] = None

            buildings[
                "number"
            ] = None

            buildings[
                "lot_area_m2"
            ] = None

            buildings[
                "built_area_m2"
            ] = None

            buildings[
                "lot_status"
            ] = None

            buildings[
                "overlap_area_m2"
            ] = None

            buildings[
                "overlap_ratio"
            ] = None

            result = (
                buildings.copy()
            )

        else:

            # =============================================
            # 18. OVERLAP AREA
            # =============================================

            intersections[
                "overlap_area_m2"
            ] = (
                intersections
                .geometry
                .area
            )


            # =============================================
            # 19. OVERLAP RATIO
            # =============================================

            intersections[
                "overlap_ratio"
            ] = (
                intersections[
                    "overlap_area_m2"
                ]
                /
                intersections[
                    "geometry_area_m2"
                ]
            )


            # =============================================
            # 20. CLIP 0 -> 1
            # =============================================

            intersections[
                "overlap_ratio"
            ] = (
                intersections[
                    "overlap_ratio"
                ]
                .clip(
                    lower=0,
                    upper=1,
                )
            )


            # =============================================
            # 21. BEST ACTIVE LOT
            # =============================================

            best_matches = (
                intersections
                .sort_values(
                    by=[
                        "building_id",
                        "overlap_area_m2",
                    ],
                    ascending=[
                        True,
                        False,
                    ],
                )
                .drop_duplicates(
                    subset=
                        "building_id",

                    keep=
                        "first",
                )
                .copy()
            )


            # =============================================
            # 22. MATCH COLUMNS
            # =============================================

            match_columns = [
                "building_id",
                "lot_id",
                "use",
                "address",
                "number",
                "lot_area_m2",
                "built_area_m2",
                "lot_status",
                "overlap_area_m2",
                "overlap_ratio",
            ]

            match_columns = [
                col
                for col
                in match_columns
                if col
                in best_matches.columns
            ]


            # =============================================
            # 23. MERGE
            # =============================================

            result = buildings.merge(
                best_matches[
                    match_columns
                ],
                on=
                    "building_id",
                how=
                    "left",
            )

            result = (
                gpd.GeoDataFrame(
                    result,
                    geometry=
                        "geometry",
                    crs=
                        GEOSAMPA_CRS,
                )
            )


    # =====================================================
    # 24. MATCH STATUS
    # =====================================================

    result[
        "has_lot_match"
    ] = (
        result[
            "lot_id"
        ]
        .notna()
    )


    # =====================================================
    # 25. USE CLASSIFICATION
    # =====================================================

    result[
        "use_classification"
    ] = (
        result.apply(
            classify_use_status,
            axis=1,
        )
    )


    # =====================================================
    # 26. MATCH QUALITY
    # =====================================================

    result[
        "match_quality"
    ] = (
        result[
            "overlap_ratio"
        ]
        .apply(
            classify_match_quality
        )
    )


    # =====================================================
    # 27. SUMMARY
    # =====================================================

    total_buildings = (
        len(result)
    )

    matched_buildings = (
        int(
            result[
                "has_lot_match"
            ]
            .sum()
        )
    )

    unmatched_buildings = (
        total_buildings
        -
        matched_buildings
    )


    use_counts = (
        result[
            "use_classification"
        ]
        .value_counts()
        .to_dict()
    )

    use_counts = {
        str(key):
            int(value)

        for key, value
        in use_counts.items()
    }


    quality_counts = (
        result[
            "match_quality"
        ]
        .value_counts()
        .to_dict()
    )

    quality_counts = {
        str(key):
            int(value)

        for key, value
        in quality_counts.items()
    }


    summary = {
        "request_id":
            request_id,

        "timestamp":
            datetime.now()
            .isoformat(
                timespec="seconds"
            ),

        "total_buildings":
            total_buildings,

        "matched_to_active_lot":
            matched_buildings,

        "without_active_lot_match":
            unmatched_buildings,

        "match_percentage":
            round(
                (
                    100
                    * matched_buildings
                    / total_buildings
                ),
                2,
            )
            if total_buildings > 0
            else 0,

        "by_use":
            use_counts,

        "by_match_quality":
            quality_counts,
    }


    # =====================================================
    # 28. DROP INTERNAL COLUMN
    # =====================================================

    if (
        "geometry_area_m2"
        in result.columns
    ):

        result = (
            result.drop(
                columns=[
                    "geometry_area_m2"
                ]
            )
        )


    # =====================================================
    # 29. TO WGS84
    # =====================================================

    result_wgs84 = (
        result.to_crs(
            INPUT_CRS
        )
    )


    # =====================================================
    # 30. UNMATCHED
    # =====================================================

    unmatched_wgs84 = (
        result_wgs84[
            ~result_wgs84[
                "has_lot_match"
            ]
        ]
        .copy()
    )


    # =====================================================
    # 31. LOW CONFIDENCE
    # =====================================================

    low_confidence_wgs84 = (
        result_wgs84[
            result_wgs84[
                "has_lot_match"
            ]
            &
            (
                result_wgs84[
                    "overlap_ratio"
                ]
                < 0.50
            )
        ]
        .copy()
    )


    # =====================================================
    # 32. SAVE RESULTS
    # =====================================================

    saved_files = {}

    if SAVE_RESULTS:

        buildings_filename = (
            f"{request_id}"
            f"_buildings.geojson"
        )

        unmatched_filename = (
            f"{request_id}"
            f"_unmatched.geojson"
        )

        low_conf_filename = (
            f"{request_id}"
            f"_low_confidence.geojson"
        )

        summary_filename = (
            f"{request_id}"
            f"_summary.json"
        )


        buildings_path = (
            RESULTS_DIR
            /
            buildings_filename
        )

        unmatched_path = (
            RESULTS_DIR
            /
            unmatched_filename
        )

        low_conf_path = (
            RESULTS_DIR
            /
            low_conf_filename
        )

        summary_path = (
            RESULTS_DIR
            /
            summary_filename
        )


        save_geojson(
            result_wgs84,
            buildings_path,
        )

        saved_files[
            "buildings"
        ] = (
            buildings_filename
        )


        if len(
            unmatched_wgs84
        ) > 0:

            save_geojson(
                unmatched_wgs84,
                unmatched_path,
            )

            saved_files[
                "unmatched"
            ] = (
                unmatched_filename
            )


        if len(
            low_confidence_wgs84
        ) > 0:

            save_geojson(
                low_confidence_wgs84,
                low_conf_path,
            )

            saved_files[
                "low_confidence"
            ] = (
                low_conf_filename
            )


        with open(
            summary_path,
            "w",
            encoding="utf-8",
        ) as f:

            json.dump(
                summary,
                f,
                ensure_ascii=False,
                indent=2,
            )


        saved_files[
            "summary"
        ] = (
            summary_filename
        )


    # =====================================================
    # 33. RESPONSE FEATURES
    # =====================================================

    features = (
        geodataframe_to_features(
            result_wgs84
        )
    )


    # =====================================================
    # 34. FINAL RESPONSE
    # =====================================================

    return {

        "request_id":
            request_id,

        "summary":
            summary,

        "files":
            saved_files,

        "type":
            "FeatureCollection",

        "features":
            features,
    }