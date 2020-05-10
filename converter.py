import xml.etree.ElementTree as ET
import argparse
from modules.finding import *
from modules.associations import *
from modules.writer import get_ttl_template, write_ontology_metadata
from modules.utils import read_drawio_xml

"""
# This lines are for compresed XML files
compressed_xml = root[0].text
coded_xml = base64.b64decode(compressed_xml)
xml_string = unquote(zlib.decompress(coded_xml, -15).decode('utf8'))
mxGraphModel = ET.fromstring(xml_string)
"""


def transform_ontology(root, filename):
    all_elements = find_elements(root)
    concepts, attribute_blocks, relations = all_elements[0:3]
    individuals, anonymous_concepts, ontology_metadata, namespaces = all_elements[3:]
    attribute_blocks = resolve_concept_reference(attribute_blocks, concepts)

    associations = concept_attribute_association(concepts, attribute_blocks)
    associations, relations = concept_relation_association(associations, relations)
    individuals = individual_type_identification(individuals, associations, relations)

    file, onto_prefix, onto_uri = get_ttl_template(filename, namespaces)
    file = write_ontology_metadata(file, ontology_metadata, onto_uri)

    file.write("#################################################################\n"
               "#    Object Properties\n"
               "#################################################################\n\n")

    for relation_id, relation in relations.items():

        if relation["type"] == "owl:ObjectProperty":
            uri = relation["uri"]
            prefix = relation["prefix"]

            file.write("### " + prefix + ":" + uri + "\n")
            file.write(prefix + ":" + uri + " rdf:type owl:ObjectProperty")
            if relation["functional"]:
                file.write(" ,\n")
                file.write("\t\t\towl:FunctionalProperty")

            if relation["symmetric"]:
                file.write(" ,\n")
                file.write("\t\t\towl:SymmetricProperty")

            if relation["transitive"]:
                file.write(" ,\n")
                file.write("\t\t\towl:TransitiveProperty")

            if relation["inverse_functional"]:
                file.write(" ,\n")
                file.write("\t\t\towl:InverseFunctionalProperty")

            if relation["domain"]:
                concept_id = relation["source"]
                concept = concepts[concept_id]
                domain_name = concept["prefix"] + ":" + concept["uri"]

                # Avoid blank nodes
                if domain_name != ":":
                    file.write(" ;\n")
                    file.write("\t\trdfs:domain " + domain_name)

            if relation["range"]:
                file.write(" ;\n")
                try:
                    concept_id = relation["target"]
                    concept = concepts[concept_id]
                    range_name = concept["prefix"] + ":" + concept["uri"]
                    file.write("\t\trdfs:range " + range_name)
                except:
                    blank_id = relation["target"]
                    group_node = anonymous_concepts[blank_id]
                    concept_ids = group_node["group"]
                    concept_names = [concepts[id]["prefix"] + ":" + concepts[id]["uri"] for id in concept_ids]
                    file.write("\t\trdfs:range [ " + group_node["type"] + " ( \n")
                    for name in concept_names:
                        file.write("\t\t\t\t\t\t" + name + "\n")

                    file.write("\t\t\t\t\t) ;\n")
                    file.write("\t\t\t\t\trdf:type owl:Class\n")
                    file.write("\t\t\t\t\t]")


            file.write(" .\n\n")


    file.write("#################################################################\n"
               "#    Data Properties\n"
               "#################################################################\n\n")

    attributes_reviewed = []
    for id, attribute_block in attribute_blocks.items():

        source_id = attribute_block["concept_associated"]

        for attribute in attribute_block["attributes"]:

            uri = attribute["uri"]
            prefix = attribute["prefix"]
            full_name = prefix + ":" + uri
            if full_name in attributes_reviewed:
                continue

            file.write("### " + prefix + ":" + uri + "\n")
            file.write(prefix + ":" + uri + " rdf:type owl:DatatypeProperty")

            if attribute["functional"]:
                file.write(" ,\n")
                file.write("\t\t\towl:FunctionalProperty")

            if attribute["domain"]:
                concept = concepts[source_id]
                domain_name = concept["prefix"] + ":" + concept["uri"]
                file.write(" ;\n")
                file.write("\t\trdfs:domain " + domain_name)

            if attribute["range"]:
                file.write(" ;\n")
                file.write("\t\trdfs:range xsd:" + attribute["datatype"].lower())

            file.write(" .\n\n")
            attributes_reviewed.append(full_name)



    file.write("#################################################################\n"
               "#    Classes\n"
               "#################################################################\n\n")

    for concept_id, association in associations.items():

        concept = association["concept"]
        concept_prefix = concept["prefix"]
        concept_uri = concept["uri"]
        # For now we are not considering unnamed concepts unless they are used for
        # relations of type owl:equivalentClass
        if concept_uri == "":
            continue
        file.write("### " + concept_prefix + ":" + concept_uri + "\n")
        file.write(concept_prefix + ":" + concept_uri + " rdf:type owl:Class")

        attribute_blocks = association["attribute_blocks"]
        relations = association["relations"]
        subclassof_statement_done = False
        for relation_id, relation in relations.items():
            if relation["type"] == "rdfs:subClassOf":
                target_id = relation["target"]
                target_name = concepts[target_id]["prefix"] + ":" + concepts[target_id]["uri"]
                file.write(" ;\n")
                file.write("\trdfs:subClassOf " + target_name)
                subclassof_statement_done = True

        for block_id, attribute_block in attribute_blocks.items():
            for attribute in attribute_block["attributes"]:
                if attribute["allValuesFrom"]:
                    if not subclassof_statement_done:
                        file.write(" ;\n")
                        file.write("\trdfs:subClassOf \n")
                        subclassof_statement_done = True
                    else:
                        file.write(" ,\n")
                    file.write("\t\t[ rdf:type owl:Restriction ;\n")
                    file.write("\t\t  owl:onProperty " + attribute["prefix"] + ":" + attribute["uri"] + " ;\n")
                    file.write("\t\t  owl:allValuesFrom xsd:" + attribute["datatype"] + " ]")

                elif attribute["someValuesFrom"]:
                    if not subclassof_statement_done:
                        file.write(" ;\n")
                        file.write("\trdfs:subClassOf \n")
                        subclassof_statement_done = True
                    else:
                        file.write(" ,\n")
                    file.write("\t\t[ rdf:type owl:Restriction ;\n")
                    file.write("\t\t  owl:onProperty " + attribute["prefix"] + ":" + attribute["uri"] + " ;\n")
                    file.write("\t\t  owl:someValuesFrom xsd:" + attribute["datatype"] + " ]")

                if attribute["min_cardinality"] is not None:
                    if not subclassof_statement_done:
                        file.write(" ;\n")
                        file.write("\trdfs:subClassOf \n")
                        subclassof_statement_done = True
                    else:
                        file.write(" ,\n")
                    file.write("\t\t[ rdf:type owl:Restriction ;\n")
                    file.write("\t\t  owl:onProperty " + attribute["prefix"] + ":" + attribute["uri"] + " ;\n")
                    file.write("\t\t  owl:minQualifiedCardinality \"" + attribute["min_cardinality"] + "\"^^xsd:" +
                               "nonNegativeInteger ;\n")
                    file.write("\t\t  owl:onDataRange xsd:" + attribute["datatype"] + " ]")

                if attribute["max_cardinality"] is not None:
                    if not subclassof_statement_done:
                        file.write(" ;\n")
                        file.write("\trdfs:subClassOf \n")
                        subclassof_statement_done = True
                    else:
                        file.write(" ,\n")
                    file.write("\t\t[ rdf:type owl:Restriction ;\n")
                    file.write("\t\t  owl:onProperty " + attribute["prefix"] + ":" + attribute["uri"] + " ;\n")
                    file.write("\t\t  owl:maxQualifiedCardinality \"" + attribute["max_cardinality"] + "\"^^xsd:" +
                               "nonNegativeInteger ;\n")
                    file.write("\t\t  owl:onDataRange xsd:" + attribute["datatype"] + " ]")

        for relation_id, relation in relations.items():
            if relation["type"] == "owl:ObjectProperty":
                if relation["allValuesFrom"]:
                    if not subclassof_statement_done:
                        file.write(" ;\n")
                        file.write("\trdfs:subClassOf \n")
                        subclassof_statement_done = True
                    else:
                        file.write(" ,\n")
                    file.write("\t\t[ rdf:type owl:Restriction ;\n")
                    file.write("\t\t  owl:onProperty " + relation["prefix"] + ":" + relation["uri"] + " ;\n")
                    # Target name only applies when the target is a class
                    if relation["target"] in concepts:
                        target_id = relation["target"]
                        target_name = concepts[target_id]["prefix"] + ":" + concepts[target_id]["uri"]
                        file.write("\t\t  owl:allValuesFrom " + target_name + " ]")
                    # Otherwise the target is an blank node of type intersection, union, etc.
                    else:
                        target_id = relation["target"]
                        group_node = anonymous_concepts[target_id]
                        concept_ids = group_node["group"]
                        concept_names = [concepts[id]["prefix"] + ":" + concepts[id]["uri"] for id in concept_ids]

                        file.write("\t\t  owl:allValuesFrom [ " + group_node["type"] + " ( \n")
                        for name in concept_names:
                            file.write("\t\t\t\t\t\t" + name + "\n")

                        file.write("\t\t\t\t\t) ;\n")
                        file.write("\t\t\t\t\trdf:type owl:Class\n")
                        file.write("\t\t\t\t\t] ]")


                elif relation["someValuesFrom"]:
                    if not subclassof_statement_done:
                        file.write(" ;\n")
                        file.write("\trdfs:subClassOf \n")
                        subclassof_statement_done = True
                    else:
                        file.write(" ,\n")
                    file.write("\t\t[ rdf:type owl:Restriction ;\n")
                    file.write("\t\t  owl:onProperty " + relation["prefix"] + ":" + relation["uri"] + " ;\n")
                    # Target name only applies when the target is a class
                    if relation["target"] in concepts:
                        target_id = relation["target"]
                        target_name = concepts[target_id]["prefix"] + ":" + concepts[target_id]["uri"]
                        file.write("\t\t  owl:someValuesFrom " + target_name + " ]")
                    # Otherwise the target is an blank node of type intersection, union, etc.
                    else:
                        target_id = relation["target"]
                        group_node = anonymous_concepts[target_id]
                        concept_ids = group_node["group"]
                        concept_names = [concepts[id]["prefix"] + ":" + concepts[id]["uri"] for id in concept_ids]
                        file.write("\t\t  owl:someValuesFrom [ " + group_node["type"] + " ( \n")
                        for name in concept_names:
                            file.write("\t\t\t\t\t\t" + name + "\n")

                        file.write("\t\t\t\t\t) ;\n")
                        file.write("\t\t\t\t\trdf:type owl:Class\n")
                        file.write("\t\t\t\t\t] ]")

                if relation["min_cardinality"] is not None:
                    if not subclassof_statement_done:
                        file.write(" ;\n")
                        file.write("\trdfs:subClassOf \n")
                        subclassof_statement_done = True
                    else:
                        file.write(" ,\n")
                    file.write("\t\t[ rdf:type owl:Restriction ;\n")
                    file.write("\t\t  owl:onProperty " + relation["prefix"] + ":" + relation["uri"] + " ;\n")
                    file.write("\t\t  owl:minQualifiedCardinality \"" + relation["min_cardinality"] + "\"^^xsd:" +
                               "nonNegativeInteger ;\n")
                    target_id = relation["target"]
                    target_name = concepts[target_id]["prefix"] + ":" + concepts[target_id]["uri"]
                    file.write("\t\t  owl:onClass " + target_name + " ]")

                if relation["max_cardinality"] is not None:
                    if not subclassof_statement_done:
                        file.write(" ;\n")
                        file.write("\trdfs:subClassOf \n")
                        subclassof_statement_done = True
                    else:
                        file.write(" ,\n")
                    file.write("\t\t[ rdf:type owl:Restriction ;\n")
                    file.write("\t\t  owl:onProperty " + relation["prefix"] + ":" + relation["uri"] + " ;\n")
                    file.write("\t\t  owl:maxQualifiedCardinality \"" + relation["max_cardinality"] + "\"^^xsd:" +
                               "nonNegativeInteger ;\n")
                    target_id = relation["target"]
                    target_name = concepts[target_id]["prefix"] + ":" + concepts[target_id]["uri"]
                    file.write("\t\t  owl:onClass " + target_name + " ]")

        for relation_id, relation in relations.items():
            if relation["type"] == "owl:disjointWith":
                file.write(" ;\n")
                target_id = relation["target"]
                target_name = concepts[target_id]["prefix"] + ":" + concepts[target_id]["uri"]
                file.write("\towl:disjointWith " + target_name)

            elif relation["type"] == "owl:equivalentClass":
                file.write(" ;\n")
                if relation["target"] in concepts:
                    complement = concepts[relation["target"]]
                    complement_name = complement["prefix"] + ":" + complement["uri"]
                    if complement_name != ":":
                        file.write("\t" + relation["type"] + " " + complement_name)
                    else:
                        file.write("\t" + relation["type"] + " [ rdf:type owl:Restriction ;\n")
                        association = associations[relation["target"]]
                        relation = list(association["relations"].items())[0][1]
                        relation_name = relation["prefix"] + ":" + relation["uri"]
                        target_id = relation["target"]
                        target_name = concepts[target_id]["prefix"] + ":" + concepts[target_id]["uri"]
                        file.write("\towl:onProperty " + relation_name + " ;\n")
                        if relation["someValuesFrom"]:
                            file.write("\towl:someValuesFrom " + target_name + " ]\n")
                        elif relation["allValuesFrom"]:
                            file.write("\towl:allValuesFrom " + target_name + " ]\n")
                elif relation["target"] in anonymous_concepts:
                    complement = anonymous_concepts[relation["target"]]
                    ids = complement["group"]
                    file.write("\t" + relation["type"] + " [ " + complement["type"] + " ( \n")
                    for id in ids:
                        concept_involved = concepts[id]["prefix"] + ":" + concepts[id]["uri"]
                        file.write("\t\t\t\t" + concept_involved + "\n")
                    file.write("\t\t\t\t)")
                    file.write("\t\t]")

        for blank_id, blank in anonymous_concepts.items():

            if len(blank["group"]) > 2:
                continue

            if concept_id in blank["group"] and blank["type"] == "owl:disjointWith":
                file.write(" ;\n")
                if blank["group"].index(concept_id) == 0:
                    complement_id = blank["group"][1]
                else:
                    complement_id = blank["group"][0]
                complement_concept = concepts[complement_id]
                complement_name = complement_concept["prefix"] + ":" + complement_concept["uri"]
                file.write("\t" + blank["type"] + " " + complement_name)

            elif concept_id in blank["group"] and blank["type"] == "owl:equivalentClass":
                file.write(" ; \n")
                if blank["group"].index(concept_id) == 0:
                    complement_id = blank["group"][1]
                else:
                    complement_id = blank["group"][0]

                if complement_id in concepts:
                    complement = concepts[complement_id]
                    complement_name = complement["prefix"] + ":" + complement["uri"]
                    if complement_name != ":":
                        file.write("\t" + blank["type"] + " " + complement_name)
                    else:
                        file.write("\t" + blank["type"] + " [ rdf:type owl:Restriction ;\n")
                        association = associations[complement_id]
                        relation = list(association["relations"].items())[0][1]
                        relation_name = relation["prefix"] + ":" + relation["uri"]
                        target_id = relation["target"]
                        target_name = concepts[target_id]["prefix"] + ":" + concepts[target_id]["uri"]
                        file.write("\towl:onProperty " + relation_name + " ;\n")
                        if relation["someValuesFrom"]:
                            file.write("\towl:someValuesFrom " + target_name + " ]\n")
                        elif relation["allValuesFrom"]:
                            file.write("\towl:allValuesFrom " + target_name + " ]\n")
                elif complement_id in anonymous_concepts:
                    complement = anonymous_concepts[complement_id]
                    ids = complement["group"]
                    file.write("\t" + blank["type"] + " [ " + complement["type"] + " ( \n")
                    for id in ids:
                        concept_involved = concepts[id]["prefix"] + ":" + concepts[id]["uri"]
                        file.write("\t\t\t\t" + concept_involved + "\n")
                    file.write("\t\t\t\t)")
                    file.write("\t\t]")

        file.write(" .\n\n")

    file.write("#################################################################\n"
               "#    Instances\n"
               "#################################################################\n\n")

    for ind_id, individual in individuals.items():

        prefix = individual["prefix"]
        uri = individual["uri"]
        type = individual["type"]
        file.write("### " + prefix + ":" + uri + "\n")
        file.write(prefix + ":" + uri + " rdf:type owl:NamedIndividual ,\n")
        file.write("\t\t" + type + " .\n\n")

    file.write("#################################################################\n"
               "#    General Axioms\n"
               "#################################################################\n\n")

    for blank_id, blank in anonymous_concepts.items():
        if len(blank["group"]) > 2 and blank["type"] in ["owl:disjointWith"]:
            file.write("[ rdf:type owl:AllDisjointClasses ;\n")
            file.write("  owl:members ( \n")

            concept_names = [concepts[id]["prefix"] + ":" + concepts[id]["uri"] for id in blank["group"]]
            for name in concept_names:
                file.write("\t\t" + name + "\n")
            file.write("\t\t)")
            file.write("] .")

def transform_rdf(root, filename):

    individuals = find_individuals(root)
    relations = find_relations(root)
    namespaces = find_namespaces(root)
    values = find_attribute_values(root)
    concepts, _ = find_concepts_and_attributes(root)

    individuals = individual_type_identification_rdf(individuals, concepts, relations)
    associations = individual_relation_association(individuals, relations)
    associations = individual_attribute_association(associations, values, relations)

    file, onto_prefix, onto_uri = get_ttl_template(filename, namespaces)

    for id, association in associations.items():

        subject = association["individual"]["prefix"] + ":" + association["individual"]["uri"]
        concept = association["individual"]["type"]
        relations = association["relations"]

        file.write(subject + " rdf:type " + concept)

        for relation_id, relation in relations.items():
            file.write(" ;\n")
            predicate = relation["prefix"] + ":" + relation["uri"]
            target_id = relation["target"]
            object = individuals[target_id]["prefix"] + ":" + individuals[target_id]["uri"]

            file.write("\t" + predicate + " " + object)

        file.write(" .\n\n")

if __name__ == "__main__":

    parser = argparse.ArgumentParser()
    parser.add_argument("diagram_path")
    parser.add_argument("output_path")
    parser.add_argument("type")
    args = parser.parse_args()

    root = read_drawio_xml(args.diagram_path)

    if args.type == "ontology":
        transform_ontology(root, args.output_path)
    elif args.type == "rdf":
        transform_rdf(root, args.output_path)
    else:
        raise ValueError("Not a correct option of data")