import sys
import hgraph_utils
from halp import directed_hypergraph
from halp.algorithms import directed_paths as hpaths
from halp.utilities import directed_statistics as stats
from halp.utilities import directed_graph_transformations as transform
import glob
import networkx as nx
import time
# library
import os


LARGE_VAL = 10000000

def main(inprefix,hedge_connectivity_file,pathway_prefix,infix,run_all):
	start = time.time()
	H, identifier2id, id2identifier = hgraph_utils.make_hypergraph(inprefix,keep_singleton_nodes=True)
	H = hgraph_utils.add_entity_set_info(H)
	G = transform.to_networkx_digraph(H)
	
	nodes = set() ## get proteins and complex members.
	node_membership = {}
	num_complexes = 0
	num_entitysets = 0
	for n in H.get_node_set():
		attrs = H.get_node_attributes(n)		
		if attrs['is_hypernode']:
			nodes.update(attrs['hypernode_members'])
			for m in attrs['hypernode_members']:
				if m not in node_membership:
					node_membership[m] = set()
				node_membership[m].add(n)
			num_complexes+=1
		if attrs['is_entityset']:
			nodes.update(attrs['entityset_members'])
			for m in attrs['entityset_members']:
				if m not in node_membership:
					node_membership[m] = set()
				node_membership[m].add(n)
			num_entitysets+=1
		nodes.add(n)
		if n not in node_membership:
			node_membership[n] = set([n])
	print('%d complexes and %d entity sets' % (num_complexes,num_entitysets))
	print('%d nodes including hypernode and entity set members' % (len(nodes)))	

	# get pathway Identifiers to Uniprot ID
	pc2uniprot,uniprot2pc = hgraph_utils.get_id_map('../../hypergraph/reactome_hypergraphs/')

	## get pathway information
	pathway_nodes,all_pathway_nodes = get_pathways(pathway_prefix,run_all=run_all)
	#print('%d pathway nodes (including hypernode members)' % (len(all_pathway_nodes)))
	#print(list(all_pathway_nodes)[:10])

	## get channels
	files = glob.glob('../../data/STRING/processed/*.txt')
	print('%d files:' % (len(files)),files)

	processed_nodes = {}
	files = ['../../data/STRING/processed/cooccurence.txt']
	for f in files:
		print('FILE %s' % (f))
		name = f.replace('../../data/STRING/processed/','').replace('.txt','')
		print('NAME %s' % (name))

		outfile_name = 'outfiles/%s-%s-positive_sets.txt' % (infix,name)
		if os.path.isfile(outfile_name):
			print('FILE %s EXISTS! Skipping.'  %(outfile_name))
			continue

		interactions = []
		missing = {}
		with open(f) as fin:
			for line in fin:
				row = line.strip().split()
				interactions.append([row[2],row[3],int(row[4])])
		print('  %d INTERACTIONS' % (len(interactions)))

		interactions_in_reactome = []
		mismapped = 0
		notinreactome = 0
		for n1,n2,val in interactions:
			if n1 in uniprot2pc and n2 in uniprot2pc:
				un1 = uniprot2pc[n1]
				un2 = uniprot2pc[n2]
			else:
				if n1 not in uniprot2pc:
					missing[n1] = ('NA','NotInPC')
				if n2 not in uniprot2pc:
					missing[n2] = ('NA','NotInPC')
				mismapped+=1
				continue
			
			if un1 in nodes and un2 in nodes:
				interactions_in_reactome.append([un1,un2,val])
			else:
				if un1 not in nodes:
					missing[n1] = (un1,'NotInHypergraph')
				if un2 not in nodes:
					missing[n2] = (un2,'NotInHypergraph')
				notinreactome+=1

		## FOR TESTING:
		##interactions_in_reactome = interactions_in_reactome[:500]

		print('  %d INTERACTIONS HAVE BOTH NODES IN REACTOME\n  %d interactions not in PathwayCommons Reactome mapping\n  %d interactions are not in this hypergraph' % (len(interactions_in_reactome),mismapped,notinreactome))
		out = open('outfiles/%s-%s-mismapped.txt' % (infix,name),'w')
		out.write('#UniProtID\tPathwayCommonsID\tMismappingReason\n')
		for m in missing:
			out.write('%s\t%s\t%s\n' % (m,missing[m][0],missing[m][1]))
		out.close()
		print('  wrote %d mismapped nodes to outfiles/%s-%s-mismapped.txt' % (len(missing),infix,name))
		sys.stdout.flush()

		interactions_in_pathways,interactions_in_same_pathway = get_pathway_interactions(interactions_in_reactome,pathway_nodes,all_pathway_nodes)
		print('  %d INTERACTIONS HAVE BOTH NODES IN THE REACTOME PATHWAYS' % (len(interactions_in_pathways)))
		print('  %d INTERACTIONS HAVE BOTH NODES IN SAME REACTOME PATHWAY' % (len(interactions_in_same_pathway)))
		sys.stdout.flush()

		## NOTE: to do whole thing replace "intearactions-in_pathways" with "interactions-in_reactome"
		b_visit_dict = hgraph_utils.make_b_visit_dict(hedge_connectivity_file,identifier2id)
		brelax_dicts,processed_nodes = preprocess_brelax_dicts(H,interactions_in_pathways,node_membership,b_visit_dict,processed_nodes)
		interactions_brelax = get_bconn_interactions(brelax_dicts,interactions_in_pathways,node_membership)
		interactions_bipartite = list(interactions_brelax.keys())
		interactions_bconn = [e for e in interactions_bipartite if interactions_brelax[e] == 0]

		print('  %d INTERACTIONS ARE Bipartite CONNECTED IN REACTOME' % (len(interactions_bipartite)))
		print('  %d INTERACTIONS ARE B-CONNECTED IN REACTOME' % (len(interactions_bconn)))
		sys.stdout.flush()

		out = open(outfile_name,'w')
		out.write('#Node1\tNode2\tScore\tAnyPathway\tSamePathway\tBipartite\tBRelaxDist\n')
		for n1,n2,val in interactions_in_reactome:
			vals = []
			if (n1,n2) in interactions_in_pathways:
				vals.append(1)
			else:
				vals.append(0)
			if (n1,n2) in interactions_in_same_pathway:
				vals.append(1)
			else:
				vals.append(0)
			if (n1,n2) in interactions_brelax:
				vals.append(1)
				vals.append(interactions_brelax[(n1,n2)])
			else:
				vals.append(0)
				vals.append(-1)
			out.write('%s\t%s\t%s\t%d\t%d\t%d\t%d\n' % (n1,n2,val,vals[0],vals[1],vals[2],vals[3]))
		out.close()
		print('  wrote outfile to %s' (outfile_name))
		sys.stdout.flush()
	end = time.time()
	print('FINAL TIME:',end-start)

def preprocess_brelax_dicts(H,interactions_in_pathways,node_membership,b_visit_dict,processed_nodes):
	node_brelax = {}
	i=0
	prev = time.time()
	
	n1_node_set = set([n1 for (n1,n2) in interactions_in_pathways])
	
	for n1 in n1_node_set:
		i+=1
		if i % 100 == 0:
			now = time.time()
			print('     %d of %d nodes (%.4f): %d have non-zero brelaxdist: %f elapsed' % (i,len(n1_node_set),i/len(n1_node_set),len(node_brelax.keys()),now-prev))
			prev = now
			sys.stdout.flush()

		if n1 in processed_nodes:
			node_brelax[n1] = processed_nodes[n1]
		else:
			n1_nodes = node_membership[n1]
			node_brelax[n1],ignore = hpaths.b_relaxation(H,n1_nodes,b_visit_dict=b_visit_dict)
			processed_nodes[n1] = node_brelax[n1]

	return node_brelax,processed_nodes

def get_bconn_interactions(brelax_dicts,interactions_in_pathways,node_membership):
	interactions_brelax = {}
	i=0
	prev = time.time()
	for n1,n2 in interactions_in_pathways:
		i+=1
		if i % 10000 == 0:
			now = time.time()
			print('     %d of %d (%.4f): %d have non-zero brelaxdist: %f elapsed' % (i,len(interactions_in_pathways),i/len(interactions_in_pathways),len(interactions_brelax.keys()),now-prev))
			prev = now
			sys.stdout.flush()

		dist_dict = brelax_dicts[n1]
		n2_nodes = node_membership[n2]

		score = LARGE_VAL
		for n in n2_nodes:
			if dist_dict[n] != None:
				score = min(score,dist_dict[n])
		if score < LARGE_VAL:
			interactions_brelax[(n1,n2)] = score

	return interactions_brelax

def get_pathway_interactions(interactions_in_reactome,pathway_nodes,all_pathway_nodes):

	interactions_in_pathways = set()
	interactions_in_same_pathway = set()
	for n1,n2,val in interactions_in_reactome:
		if n1 in all_pathway_nodes and n2 in all_pathway_nodes:
			interactions_in_pathways.add((n1,n2))
			for p in pathway_nodes:
				if n1 in pathway_nodes[p] and n2 in pathway_nodes[p]:
					interactions_in_same_pathway.add((n1,n2))
					break
	return interactions_in_pathways,interactions_in_same_pathway

# def get_pathways(pathway_prefix):
# 	## NEW STEP - get interactions in pathway.
# 	#pathways = read_pathways_from_brelax(pathway_prefix)
# 	pathways = read_pathways_from_hypergraphs(pathway_prefix)
# 	print('%d pathways' % (len(pathways)))
# 	all_pathway_nodes = set()
# 	pathway_nodes = {}
# 	for p in pathways:
# 		pathway_nodes[p] = set()
# 		for n in pathways[p]:
# 			attrs = H.get_node_attributes(n)
# 			if attrs['is_hypernode']:
# 				pathway_nodes[p].update(attrs['hypernode_members'])
# 			if attrs['is_entityset']:
# 				pathway_nodes[p].update(attrs['entityset_members'])
# 			pathway_nodes[p].add(n)
# 		all_pathway_nodes.update(pathway_nodes[p])
# 	return pathway_nodes,all_pathway_nodes

def get_pathways(pathway_prefix,run_all=False):

	# these are the "top lvel" reactome pathways - they are too general. Ignore.
	TO_IGNORE = ['Circadian-Clock', 'Cell-Cycle', 'Disease',  'Programmed-Cell-Death',  'Extracellular-matrix-organization',  'Vesicle-mediated-transport', \
	 'Cellular-responses-to-external-stimuli',  'Organelle-biogenesis-and-maintenance',  'Neuronal-System',  'NICD-traffics-to-nucleus',  'Signaling-Pathways',  \
	 'Metabolism-of-RNA',  'DNA-Repair',  'Metabolism',  'Mitophagy',  'Gene-expression-(Transcription)',  'Developmental-Biology',  'Chromatin-organization', \
	 'Transport-of-small-molecules',  'Immune-System',  'Metabolism-of-proteins',  'Muscle-contraction',  'Digestion-and-absorption',  'Reproduction', \
	  'Hemostasis',  'Cell-Cell-communication']

	ORIG_34 =['Signaling-by-EGFR','Signaling-by-ERBB2','Signaling-by-ERBB4','PI3K-AKT-Signaling','Signaling-by-MET',
'Signaling-by-FGFR','ERK1-ERK2-pathway','Signaling-by-Type-1-Insulin-like-Growth-Factor-1-Receptor-(IGF1R)', 'Signaling-by-Insulin-receptor', 
'Integrin-signaling','Signaling-by-GPCR','DAG-and-IP3-signaling','Signaling-by-PDGF', 'Signaling-by-VEGF', 'Signaling-by-NTRKs',
'Signaling-by-WNT', 'TNF-signaling', 'Signaling-by-PTK6',   
'Signaling-by-TGF-beta-Receptor-Complex', 'TRAIL-signaling','FasL--CD95L-signaling','Signaling-by-NOTCH', 'Signaling-by-BMP', 'Signaling-by-Activin',  'MAPK6-MAPK4-signaling', 'p75-NTR-receptor-mediated-signalling', 'Signaling-by-SCF-KIT','Signaling-by-Hedgehog','Signaling-by-Nuclear-Receptors', 'Signaling-by-Leptin', 'Signaling-by-Hippo','Signaling-by-Rho-GTPases','Signaling-by-MST1','mTOR-signalling']  
	
	print(pathway_prefix)
	files = glob.glob('%s/*-hypernodes.txt' % (pathway_prefix))
	print('%d files' % (len(files)))
	pathway_nodes = {}
	for f in files:
		name = f.replace(pathway_prefix,'').replace('-hypernodes.txt','')
		# to only do the 34 originals
		if not run_all and name not in ORIG_34:
			continue
		#print(name)
		pathway_nodes[name] = set()
		with open(f) as fin:
			for line in fin:
				if line[0] == '#':
					continue
				row = line.strip().split()
				#print(row)
				pathway_nodes[name].add(row[0])
				if len(row) > 1:
					pathway_nodes[name].update(row[1].split(';'))
	
	print('%d pathways' % (len(pathway_nodes)))

	if run_all: # ignore top-level ones and remove redundants.
		for i in TO_IGNORE:
			del pathway_nodes[i]
		print('%d pathways after removing top-level pathways' % (len(pathway_nodes)))

		#to remove redundants
		to_remove = set()
		pathway_list = list(pathway_nodes.keys())
		for i in pathway_list:
			for j in pathway_list:
				if i != j and len(pathway_nodes[i].intersection(pathway_nodes[j])) == len(pathway_nodes[i]):
					to_remove.add(i)
					break
		print('Removing %d redundant sets' % (len(to_remove)))
		for t in to_remove:
			del pathway_nodes[t]


	print('%d pathways remain' % (len(pathway_nodes)))
	if len(pathway_nodes) < 25:
		for p in pathway_nodes:
			print('  %s' % (p))

	all_pathway_nodes = set()
	for p in pathway_nodes:
		all_pathway_nodes.update(pathway_nodes[p])
	
	return pathway_nodes,all_pathway_nodes

def read_functional_interactions():
	svd_file = '../../data/STRING/96066.protein.links.cooccurence.v11.0.txt.mapped'
	interactions = []
	with open(svd_file) as fin:
		for line in fin:
			if line[0] == '#': 
				continue
			row = line.strip().split()
			interactions.append([row[0],row[1],int(row[2])])
	return interactions

def read_pathways_from_brelax(prefix):
	files = glob.glob(prefix+'*')
	print('%d files' % (len(files)))
	pathways = {}
	for f in files:
		pathway_name = f.replace(prefix,'').replace('_b_relax.txt','')
		print('reading %s' % (pathway_name))
		pathways[pathway_name] = {}
		with open(f) as fin:
			for line in fin:
				if line[0:2] != '-1':
					continue
				row = line.strip().split('\t')
				pathways[pathway_name] = set(row[2].split(';'))
	return pathways

if __name__ == '__main__':
	if len(sys.argv) != 5 and len(sys.argv) != 6:
		print('Usage: python3 run-channels.py <HYPERGRAPH_PREFIX> <hedge_connectivity_file> <pathway_brelax_prefix> <infix> <RUN_ALL - optional, any word here is ok>')
	if len(sys.argv)==5:
		main(sys.argv[1],sys.argv[2],sys.argv[3],sys.argv[4],False)
	elif len(sys.argv) == 6:
		main(sys.argv[1],sys.argv[2],sys.argv[3],sys.argv[4],True)
