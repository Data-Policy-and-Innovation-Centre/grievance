# Create an empty db
-- Connect as root or an admin user
mysql -uroot -p

-- At the mysql> prompt:
DROP DATABASE IF EXISTS myapp_db;
CREATE DATABASE   myapp_db CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
EXIT;

-- At the command
mysql -u myapp -pdpic -h127.0.0.1 -P3306 myapp_db

-- At the mysql> prompt:
SOURCE D:/Dump20250730.sql;
SHOW TABLES;

SELECT COUNT(DISTINCT trackingId) AS distinct_tracking_count FROM t_janasunani_etl_history_pre_data;
SELECT COUNT(DISTINCT trackingId) AS distinct_tracking_count FROM t_janasunani_etl_pre_data;

WITH actions AS (SELECT DISTINCT trackingId FROM t_janasunani_etl_history_pre_data) SELECT COUNT(*) AS intersecting_rows  FROM t_janasunani_etl_pre_data AS c INNER JOIN actions AS a ON c.trackingId = a.trackingId;


# Intersection
SELECT COUNT(DISTINCT c.trackingId) AS intersecting_ids FROM t_janasunani_etl_pre_data AS c INNER JOIN t_janasunani_etl_history_pre_data AS a ON c.trackingId = a.trackingId;

# Only in complaints data
SELECT COUNT(*) AS only_in_pre_data FROM t_janasunani_etl_pre_data c WHERE NOT EXISTS (SELECT 1 FROM t_janasunani_etl_history_pre_data a WHERE a.trackingId = c.trackingId);

# Only in action_history data
SELECT YEAR(action_taken_date) as year, COUNT(DISTINCT a.trackingId) AS only_in_history_pre_data FROM t_janasunani_etl_history_pre_data a WHERE NOT EXISTS (SELECT 1 FROM t_janasunani_etl_pre_data c WHERE c.trackingId = a.trackingId) AND a.action_taken_date IS NOT NULL GROUP BY year;


# missing values per column
SELECT
  SUM(col1 IS NULL) AS col1_missing,
  SUM(col2 IS NULL) AS col2_missing,
  SUM(col3 IS NULL) AS col3_missing
FROM your_table;

SELECT
  SUM(createdYear            IS NULL) AS createdYear_missing,
  SUM(ticketNumber           IS NULL) AS ticketNumber_missing,
  SUM(petitionerName         IS NULL) AS petitionerName_missing,
  SUM(petitionerMobile       IS NULL) AS petitionerMobile_missing,
  SUM(petitionerEmail        IS NULL) AS petitionerEmail_missing,
  SUM(grievanceSubject       IS NULL) AS grievanceSubject_missing,
  SUM(Document               IS NULL) AS Document_missing,
  SUM(intOfficeId            IS NULL) AS intOfficeId_missing,
  SUM(officeName             IS NULL) AS officeName_missing,
  SUM(RecievedBy             IS NULL) AS RecievedBy_missing,
  SUM(RecievedByOfficerName  IS NULL) AS RecievedByOfficerName_missing,
  SUM(intDistId              IS NULL) AS intDistId_missing,
  SUM(districtName           IS NULL) AS districtName_missing,
  SUM(intBlockId             IS NULL) AS intBlockId_missing,
  SUM(blockName              IS NULL) AS blockName_missing,
  SUM(Mode                    IS NULL) AS Mode_missing,
  SUM(modeName               IS NULL) AS modeName_missing,
  SUM(disabilityType         IS NULL) AS disabilityType_missing,
  SUM(disbilityName          IS NULL) AS disbilityName_missing,
  SUM(intCompliantStatusId   IS NULL) AS intCompliantStatusId_missing,
  SUM(StatusName             IS NULL) AS StatusName_missing,
  SUM(govtTicket             IS NULL) AS govtTicket_missing,
  SUM(CreatedOn              IS NULL) AS CreatedOn_missing,
  SUM(taggedTo               IS NULL) AS taggedTo_missing,
  SUM(taggedBy               IS NULL) AS taggedBy_missing,
  SUM(taggedByName           IS NULL) AS taggedByName_missing,
  SUM(taggedDate             IS NULL) AS taggedDate_missing,
  SUM(CategoryId             IS NULL) AS CategoryId_missing,
  SUM(category               IS NULL) AS category_missing,
  SUM(DepartmentId           IS NULL) AS DepartmentId_missing,
  SUM(deptName               IS NULL) AS deptName_missing,
  SUM(SubCategoryId          IS NULL) AS SubCategoryId_missing,
  SUM(Subcategory            IS NULL) AS Subcategory_missing,
  SUM(intStateId             IS NULL) AS intStateId_missing,
  SUM(stateName              IS NULL) AS stateName_missing,
  SUM(gender                 IS NULL) AS gender_missing,
  SUM(genderName             IS NULL) AS genderName_missing,
  SUM(transferStatus         IS NULL) AS transferStatus_missing,
  SUM(mostUrgent             IS NULL) AS mostUrgent_missing,
  SUM(reviewAuthority        IS NULL) AS reviewAuthority_missing,
  SUM(reviewAuthorityName    IS NULL) AS reviewAuthorityName_missing,
  SUM(pendingWith            IS NULL) AS pendingWith_missing,
  SUM(pendingwithName        IS NULL) AS pendingwithName_missing,
  SUM(vchAllEscUser          IS NULL) AS vchAllEscUser_missing,
  SUM(assignedOn             IS NULL) AS assignedOn_missing,
  SUM(escalationDate         IS NULL) AS escalationDate_missing,
  SUM(isSelfAssign           IS NULL) AS isSelfAssign_missing,
  SUM(ResolvedOn             IS NULL) AS ResolvedOn_missing,
  SUM(resolvedBy             IS NULL) AS resolvedBy_missing,
  SUM(updatedBy              IS NULL) AS updatedBy_missing,
  SUM(lastUpdatedOn          IS NULL) AS lastUpdatedOn_missing,
  SUM(benefitted             IS NULL) AS benefitted_missing,
  SUM(Address                IS NULL) AS Address_missing,
  SUM(reopenedBy             IS NULL) AS reopenedBy_missing,
  SUM(vchAccount             IS NULL) AS vchAccount_missing,
  SUM(trackingId             IS NULL) AS trackingId_missing
FROM t_janasunani_etl_pre_data;