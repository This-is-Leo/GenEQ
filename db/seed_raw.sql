-- Provinces
INSERT INTO provinces (code, name) VALUES
 ('BC','British Columbia'), ('AB','Alberta'), ('SK','Saskatchewan'),
 ('MB','Manitoba'), ('ON','Ontario'), ('QC','Quebec'),
 ('NB','New Brunswick'), ('NS','Nova Scotia'), ('PEI','Prince Edward Island'),
 ('NL','Newfoundland and Labrador'),
 ('NT','Northwest Territories'), ('YK','Yukon'), ('NU','Nunavut');

-- Raw province AI exposure (exact from your graph)
INSERT INTO province_risk_raw (province_code, exposure_value) VALUES
 ('BC', 16), ('AB', 18.2), ('SK', 19.6), ('MB', 15.6),
 ('ON', 15.7), ('QC', 15.2), ('NB', 13.8), ('NS', 15.3),
 ('PEI', 14.3), ('NL', 15), ('NT', 18.8), ('YK', 17.4), ('NU', 10.9);

-- Ethnicities
INSERT INTO ethnicities (code, name) VALUES
 ('white','Not a visible minority'),
 ('south_asian','South Asian'),
 ('chinese','Chinese'),
 ('black','Black'),
 ('filipino','Filipino'),
 ('latin_american','Latin American'),
 ('southeast_asian','Southeast Asian'),
 ('arab','Arab'),
 ('west_asian','West Asian'),
 ('korean','Korean'),
 ('japanese','Japanese'),
 ('multiple_visible_minority','Multiple visible minorities'),
 ('visible_minority','Visible minority, n.i.e.');

-- Raw ethnicity AI exposure
INSERT INTO ethnicity_risk_raw (ethnicity_code, exposure_value) VALUES
 ('white', 0.42),
 ('south_asian', 0.41),
 ('chinese', 0.43),
 ('black', 0.39),
 ('filipino', 0.37),
 ('latin_american', 0.39),
 ('southeast_asian', 0.39),
 ('arab', 0.42),
 ('west_asian', 0.42),
 ('korean', 0.41),
 ('japanese', 0.41),
 ('multiple_visible_minority', 0.40),
 ('visible_minority', 0.40);