#!/usr/bin/env python3
"""
Seed Neo4j with sample network topology data for the lungo demo.
This creates a realistic network graph with devices, links, and services.
"""

import os
import sys
import time
from neo4j import GraphDatabase

NEO4J_URI = os.getenv("NEO4J_URI", "bolt://localhost:7687")
NEO4J_USER = os.getenv("NEO4J_USER", "neo4j")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD", "password123")

def wait_for_neo4j(max_retries=30, delay=2):
    """Wait for Neo4j to be ready."""
    driver = None
    for i in range(max_retries):
        try:
            driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))
            with driver.session() as session:
                session.run("RETURN 1")
            print(f"Connected to Neo4j at {NEO4J_URI}")
            return driver
        except Exception as e:
            print(f"Waiting for Neo4j... ({i+1}/{max_retries}): {e}")
            time.sleep(delay)
    print("Failed to connect to Neo4j")
    sys.exit(1)

def seed_data(driver):
    """Seed the database with network topology data."""
    with driver.session() as session:
        # Clear existing data
        session.run("MATCH (n) DETACH DELETE n")
        print("Cleared existing data")

        # Create network topology
        cypher = """
        // Core Router
        CREATE (core:Device:Router {name: 'core-router-1', type: 'router', location: 'datacenter-1'})

        // Aggregation Switches
        CREATE (agg1:Device:Switch {name: 'agg-switch-1', type: 'switch', location: 'datacenter-1'})
        CREATE (agg2:Device:Switch {name: 'agg-switch-2', type: 'switch', location: 'datacenter-1'})
        CREATE (agg3:Device:Switch {name: 'agg-switch-3', type: 'switch', location: 'datacenter-2'})

        // Distribution Switches (ToR)
        CREATE (dist1:Device:Switch {name: 'dist-switch-1', type: 'tor-switch', location: 'rack-1'})
        CREATE (dist2:Device:Switch {name: 'dist-switch-2', type: 'tor-switch', location: 'rack-2'})
        CREATE (dist3:Device:Switch {name: 'dist-switch-3', type: 'tor-switch', location: 'rack-3'})

        // Servers (hosts for services)
        CREATE (srv1:Device:Server {name: 'app-server-1', type: 'server', location: 'rack-1'})
        CREATE (srv2:Device:Server {name: 'db-server-1', type: 'server', location: 'rack-2'})
        CREATE (srv3:Device:Server {name: 'mcp-server-1', type: 'server', location: 'rack-2'})
        CREATE (srv4:Device:Server {name: 'farm-server-brazil', type: 'server', location: 'rack-3'})
        CREATE (srv5:Device:Server {name: 'farm-server-colombia', type: 'server', location: 'rack-3'})
        CREATE (srv6:Device:Server {name: 'farm-server-vietnam', type: 'server', location: 'rack-3'})

        // Network Links
        CREATE (link_core_agg1:Link {id: 'link-core-agg1', status: 'active', utilization: 45, bandwidth: '10Gbps'})
        CREATE (link_core_agg2:Link {id: 'link-core-agg2', status: 'active', utilization: 52, bandwidth: '10Gbps'})
        CREATE (link_core_agg3:Link {id: 'link-core-agg3', status: 'degraded', utilization: 87, bandwidth: '10Gbps'})
        CREATE (link_agg1_dist1:Link {id: 'link-agg1-dist1', status: 'active', utilization: 35, bandwidth: '1Gbps'})
        CREATE (link_agg2_dist2:Link {id: 'link-agg2-dist2', status: 'active', utilization: 62, bandwidth: '1Gbps'})
        CREATE (link_agg3_dist3:Link {id: 'link-agg3-dist3', status: 'degraded', utilization: 91, bandwidth: '1Gbps'})
        CREATE (link_dist1_srv1:Link {id: 'link-d1-srv1', status: 'active', utilization: 25, bandwidth: '1Gbps'})
        CREATE (link_dist2_srv2:Link {id: 'link-d2-srv2', status: 'active', utilization: 78, bandwidth: '1Gbps'})
        CREATE (link_dist2_srv3:Link {id: 'link-d2-srv3', status: 'active', utilization: 40, bandwidth: '1Gbps'})
        CREATE (link_dist3_srv4:Link {id: 'link-d3-srv4', status: 'active', utilization: 30, bandwidth: '1Gbps'})
        CREATE (link_dist3_srv5:Link {id: 'link-d3-srv5', status: 'active', utilization: 28, bandwidth: '1Gbps'})
        CREATE (link_dist3_srv6:Link {id: 'link-d3-srv6', status: 'active', utilization: 32, bandwidth: '1Gbps'})

        // Services
        CREATE (svc_auction:Service {name: 'lungo_auction_supervisor', critical: true, port: 8000})
        CREATE (svc_db:Service {name: 'postgresql_orders', critical: true, port: 5432})
        CREATE (svc_weather:Service {name: 'weather_service', critical: false, port: 8125})
        CREATE (svc_slim:Service {name: 'slim_gateway', critical: true, port: 46357})
        CREATE (svc_brazil:Service {name: 'brazil_farm_agent', critical: false, port: 9999})
        CREATE (svc_colombia:Service {name: 'colombia_farm_agent', critical: false, port: 9999})
        CREATE (svc_vietnam:Service {name: 'vietnam_farm_agent', critical: false, port: 9999})

        // Device connections (through links)
        CREATE (core)-[:CONNECTS_TO]->(link_core_agg1)-[:CONNECTS_TO]->(agg1)
        CREATE (core)-[:CONNECTS_TO]->(link_core_agg2)-[:CONNECTS_TO]->(agg2)
        CREATE (core)-[:CONNECTS_TO]->(link_core_agg3)-[:CONNECTS_TO]->(agg3)
        CREATE (agg1)-[:CONNECTS_TO]->(link_agg1_dist1)-[:CONNECTS_TO]->(dist1)
        CREATE (agg2)-[:CONNECTS_TO]->(link_agg2_dist2)-[:CONNECTS_TO]->(dist2)
        CREATE (agg3)-[:CONNECTS_TO]->(link_agg3_dist3)-[:CONNECTS_TO]->(dist3)
        CREATE (dist1)-[:CONNECTS_TO]->(link_dist1_srv1)-[:CONNECTS_TO]->(srv1)
        CREATE (dist2)-[:CONNECTS_TO]->(link_dist2_srv2)-[:CONNECTS_TO]->(srv2)
        CREATE (dist2)-[:CONNECTS_TO]->(link_dist2_srv3)-[:CONNECTS_TO]->(srv3)
        CREATE (dist3)-[:CONNECTS_TO]->(link_dist3_srv4)-[:CONNECTS_TO]->(srv4)
        CREATE (dist3)-[:CONNECTS_TO]->(link_dist3_srv5)-[:CONNECTS_TO]->(srv5)
        CREATE (dist3)-[:CONNECTS_TO]->(link_dist3_srv6)-[:CONNECTS_TO]->(srv6)

        // Services running on servers
        CREATE (svc_auction)-[:RUNS_ON]->(srv1)
        CREATE (svc_db)-[:RUNS_ON]->(srv2)
        CREATE (svc_weather)-[:RUNS_ON]->(srv3)
        CREATE (svc_slim)-[:RUNS_ON]->(srv1)
        CREATE (svc_brazil)-[:RUNS_ON]->(srv4)
        CREATE (svc_colombia)-[:RUNS_ON]->(srv5)
        CREATE (svc_vietnam)-[:RUNS_ON]->(srv6)

        // Service dependencies
        CREATE (svc_auction)-[:DEPENDS_ON]->(svc_db)
        CREATE (svc_auction)-[:DEPENDS_ON]->(svc_slim)
        CREATE (svc_brazil)-[:DEPENDS_ON]->(svc_slim)
        CREATE (svc_colombia)-[:DEPENDS_ON]->(svc_slim)
        CREATE (svc_colombia)-[:DEPENDS_ON]->(svc_weather)
        CREATE (svc_vietnam)-[:DEPENDS_ON]->(svc_slim)

        RETURN 'Network topology created successfully'
        """
        result = session.run(cypher)
        print(result.single()[0])

        # Verify data
        count_result = session.run("""
            MATCH (d:Device) WITH count(d) as devices
            MATCH (l:Link) WITH devices, count(l) as links
            MATCH (s:Service) WITH devices, links, count(s) as services
            RETURN devices, links, services
        """)
        counts = count_result.single()
        print(f"Created: {counts['devices']} devices, {counts['links']} links, {counts['services']} services")

def main():
    print(f"Seeding Neo4j at {NEO4J_URI}")
    driver = wait_for_neo4j()
    try:
        seed_data(driver)
        print("Database seeded successfully!")
    finally:
        driver.close()

if __name__ == "__main__":
    main()
