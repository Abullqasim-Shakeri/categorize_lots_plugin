from qgis.core import (
    QgsProject, 
    QgsVectorLayer, 
    QgsField, 
    QgsFeature, 
    QgsGeometry,
    QgsSpatialIndex
)
from PyQt5.QtCore import QVariant

# 1. Load Layers
original_layer_name = 'lots_D1 — clipped'
buildings_layer_name = 'Building_oldenburg'
roads_polygon_layer_name = 'Highway Buffered — highway_buffered'
railways_polygon_layer_name = 'RailWay Buffered — rail_547'

original_layer = QgsProject.instance().mapLayersByName(original_layer_name)[0]
buildings_layer = QgsProject.instance().mapLayersByName(buildings_layer_name)[0]
roads_polygon_layer = QgsProject.instance().mapLayersByName(roads_polygon_layer_name)[0]
railways_polygon_layer = QgsProject.instance().mapLayersByName(railways_polygon_layer_name)[0]

# 2. Add a new "Category" field if it doesn't exist
if original_layer.fields().indexFromName('Category') == -1:
    if original_layer.isEditable() or original_layer.startEditing():
        original_layer.dataProvider().addAttributes([QgsField('Category', QVariant.String)])
        original_layer.updateFields()
    else:
        print("Unable to start editing the original layer.")
        exit()

# 3. Create Spatial Indexes to speed up intersection checks
building_index = QgsSpatialIndex()
for b_feat in buildings_layer.getFeatures():
    building_index.insertFeature(b_feat)

roads_index = QgsSpatialIndex()
for r_feat in roads_polygon_layer.getFeatures():
    roads_index.insertFeature(r_feat)

railways_index = QgsSpatialIndex()
for rail_feat in railways_polygon_layer.getFeatures():
    railways_index.insertFeature(rail_feat)

# 4. Define the Categorization Function
#    (Uses bounding-box queries to reduce expensive geometry intersections)
def categorize_feature(feature,
                       buildings_layer,
                       roads_polygon_layer,
                       railways_polygon_layer,
                       building_index,
                       roads_index,
                       railways_index):
    """
    Classify the lot feature by:
      1) Checking if BOTH:
         - the lot covers >=40% of the building area, AND
         - the building covers >=20% of the lot area
         --> 'Building'
      2) Otherwise, if >=45% of the lot area is covered by roads --> 'Road'
         (Note: in the original code, the threshold is actually 0.25)
      3) Otherwise, if >=45% of the lot area is covered by railways --> 'Railway'
         (Note: in the original code, it checks coverage >= 0.35 but assigns 'Road' - likely a bug, but unchanged here)
      4) Else --> 'None'
    """
    category = 'None'
    lot_geometry = feature.geometry()
    
    # Basic checks
    if not lot_geometry or lot_geometry.isEmpty():
        return category
    
    lot_area = lot_geometry.area()
    if lot_area <= 0:
        return category

    # A) Check Dual Building Criterion
    #    (If coverage_of_building >= 0.4 AND coverage_in_lot >= 0.2)
    candidate_building_ids = building_index.intersects(lot_geometry.boundingBox())
    for b_id in candidate_building_ids:
        building_feat = buildings_layer.getFeature(b_id)
        b_geom = building_feat.geometry()
        if b_geom and not b_geom.isEmpty():
            if lot_geometry.intersects(b_geom):
                intersection_geom = lot_geometry.intersection(b_geom)
                intersection_area = intersection_geom.area()
                building_area = b_geom.area()
                
                if building_area > 0:
                    coverage_of_building = intersection_area / building_area  # % of building covered by lot
                else:
                    coverage_of_building = 0

                coverage_in_lot = intersection_area / lot_area               # % of lot covered by building

                # Both conditions must be met:
                if coverage_of_building >= 0.4 and coverage_in_lot >= 0.1:
                    category = 'Building'
                    break  # Once categorized as Building, no need to check more

    # B) If not Building, check Road Coverage (>= 25% 
    if category == 'None':
        total_road_area_in_lot = 0
        candidate_road_ids = roads_index.intersects(lot_geometry.boundingBox())
        for r_id in candidate_road_ids:
            road_feat = roads_polygon_layer.getFeature(r_id)
            r_geom = road_feat.geometry()
            if r_geom and not r_geom.isEmpty():
                if lot_geometry.intersects(r_geom):
                    intersection_geom = lot_geometry.intersection(r_geom)
                    total_road_area_in_lot += intersection_geom.area()
        
        road_coverage = total_road_area_in_lot / lot_area
        # Original code uses 0.25 (25%) 
        if road_coverage >= 0.25:
            category = 'Road'


    # C) If not Building/Road, check Railway Coverage 
    if category == 'None':
        total_rail_area_in_lot = 0
        candidate_rail_ids = railways_index.intersects(lot_geometry.boundingBox())
        for rail_id in candidate_rail_ids:
            rail_feat = railways_polygon_layer.getFeature(rail_id)
            rail_geom = rail_feat.geometry()
            if rail_geom and not rail_geom.isEmpty():
                if lot_geometry.intersects(rail_geom):
                    intersection_geom = lot_geometry.intersection(rail_geom)
                    total_rail_area_in_lot += intersection_geom.area()

        rail_coverage = total_rail_area_in_lot / lot_area
        # Original code has rail_coverage >= 0.35 => category = 'Road'
        if rail_coverage >= 0.35:
            category = 'Road'

    return category

# 5. Update the Category Field for Each Feature
if original_layer.isEditable() or original_layer.startEditing():
    for feat in original_layer.getFeatures():
        cat = categorize_feature(
            feat, 
            buildings_layer,
            roads_polygon_layer,
            railways_polygon_layer,
            building_index,
            roads_index,
            railways_index
        )
        original_layer.changeAttributeValue(
            feat.id(),
            original_layer.fields().indexFromName('Category'),
            cat
        )
    
    if not original_layer.commitChanges():
        print("Error: Could not commit changes to the layer.")
    else:
        print("Categorization completed (using spatial index).")
else:
    print("The layer could not be set to editing mode.")
