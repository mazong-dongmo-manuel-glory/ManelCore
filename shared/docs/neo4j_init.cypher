// Constraints for uniqueness
CREATE CONSTRAINT company_id IF NOT EXISTS FOR (c:Company) REQUIRE c.id IS UNIQUE;
CREATE CONSTRAINT opportunity_url IF NOT EXISTS FOR (o:Opportunity) REQUIRE o.url IS UNIQUE;
CREATE CONSTRAINT sector_name IF NOT EXISTS FOR (s:Sector) REQUIRE s.name IS UNIQUE;
CREATE CONSTRAINT contact_email IF NOT EXISTS FOR (c:Contact) REQUIRE c.email IS UNIQUE;

// Indexes for performance
CREATE INDEX opportunity_status IF NOT EXISTS FOR (o:Opportunity) ON (o.status);
CREATE INDEX message_timestamp IF NOT EXISTS FOR (m:Message) ON (m.timestamp);

// Initial Metadata
MERGE (s1:Sector {name: 'Construction'});
MERGE (s2:Sector {name: 'TI'});
MERGE (s3:Sector {name: 'Services Professionnels'});
