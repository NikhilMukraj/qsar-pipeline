from rdkit import Chem
from rdkit.Chem import Descriptors
from rdkit.Chem import Lipinski
from rdkit.Chem.FilterCatalog import FilterCatalog, FilterCatalogParams
import numpy as np
import pandas as pd
import json
import sys
import os
os.environ['TF_CPP_MIN_LOG_LEVEL'] = '3' 
from tensorflow.keras import models
from smiles_tools import return_tokens
from smiles_tools import SmilesEnumerator
from c_wrapper import seqOneHot
from ml_scorer import get_score
import string_ga
from functools import lru_cache


GREEN = '\033[1;32m'
NC = '\033[0m'
RED='\033[0;31m'

if len(sys.argv) < 3:
    print(f"{RED}Too few args...{NC}")
    sys.exit()

with open(sys.argv[1], 'r') as f:
    contents = json.load(f)

necessary_args = {
    'population_size': [int],
    'mating_pool_size': [int], 
    'generations': [int], 
    'mutation_rate': [float], 
    'seed': [int, type(None)], 
    'average_size': [float], 
    'size_stdev': [float], 
    'string_type': [str], 
    'scoring_function': [list], 
    'augment': [list], 
    'max_len': [int], 
    'max_score': [float], 
    'prune_population': [bool], 
    'target': [list], 
    'file_name': [str],
}

for i in contents.keys():
    if i not in necessary_args.keys():
        print(f'{RED}Unknown argument: {i}{NC}')
        sys.exit(1)

for i in necessary_args.keys():
    if i not in contents.keys():
        print(f'{RED}Missing argument: {i}{NC}')
        sys.exit(1)

for key, value in contents.items():
    if type(value) not in necessary_args[key]:
        print(f'{RED}Type mismatch in argument, expected type in {necessary_args[key]} at "{key}" argument but got {type(value)}{NC}')
        sys.exit(1)

if type(contents['augment'][0]) != bool:
    print(f'{RED}Type mismatch in argument, expected type {bool} at "augment" argument at first index but got {type(contents["augment"][0])}{NC}')
    sys.exit(1)

if type(contents['augment'][1]) != int:
    print(f'{RED}Type mismatch in argument, expected type {int} at "augment" argument at second but got {type(contents["augment"][1])}{NC}')
    sys.exit(1)

if any(type(i) != str for i in contents['scoring_function']):
    print(f'{RED}Type mistmatch in argument, expected type {str} in "scoring_function"{NC}')
    sys.exit(1)

def get_qed(molecule):
    qed = 0
    
    molecular_weight = Descriptors.ExactMolWt(molecule)
    logp = Descriptors.MolLogP(molecule)
    h_bond_donor = Descriptors.NumHDonors(molecule)
    h_bond_acceptors = Descriptors.NumHAcceptors(molecule)
    rotatable_bonds = Descriptors.NumRotatableBonds(molecule)
    num_of_rings = Chem.rdMolDescriptors.CalcNumRings(molecule)

    if molecular_weight < 400:
        qed += 1/6
    if num_of_rings > 0:
        qed += 1/6
    if rotatable_bonds < 5:
        qed += 1/6
    if h_bond_donor <= 5:
        qed += 1/6
    if h_bond_acceptors <= 10:
        qed += 1/6
    if logp < 5:
        qed += 1/6
        
    return qed

def get_lipinski(molecule):
    lipi = 0

    h_bond_donors = Lipinski.NumHDonors(molecule)
    h_bond_acceptors = Descriptors.NumHAcceptors(molecule)
    molecular_weight = Descriptors.ExactMolWt(molecule)
    logp = Descriptors.MolLogP(molecule)

    if h_bond_donors <= 5:
        lipi += .25
    if h_bond_acceptors <= 10:
        lipi += .25
    if 200 <= molecular_weight <= 500:
        lipi += .25
    if logp <= 5:
        lipi += .25

    return lipi   

def get_custom_lipinski(molecule):
    if string_ga.current_generation['gen'] > contents['generations'] / 2 and Descriptors.ExactMolWt(molecule) <= 200:
        return .1
    else: 
        return get_lipinski(molecule)

def get_ghose(molecule):
    ghose = 0

    molecular_weight = Descriptors.ExactMolWt(molecule)
    logp = Descriptors.MolLogP(molecule)
    number_of_atoms = Chem.rdchem.Mol.GetNumAtoms(molecule)
    molar_refractivity = Chem.Crippen.MolMR(molecule)

    if 160 <= molecular_weight <= 480:
        ghose += .25
    if -.4 <= logp <= 5.6:
        ghose += .25
    if 20 <= number_of_atoms <= 70:
        ghose += .25
    if 40 <= molar_refractivity <= 130:
        ghose += .25

    return ghose

params = FilterCatalogParams()
params.AddCatalog(FilterCatalogParams.FilterCatalogs.PAINS)
catalog = FilterCatalog(params)

def get_pains(molecule):
    isPAINS = catalog.GetFirstMatch(molecule)
    return int(isPAINS is None)

drug_likeness_parser = {
    'lipinski': get_lipinski, 
    'custom_lipinski': get_custom_lipinski,
    'qed': get_qed, 
    'ghose': get_ghose,
    'pains': get_pains,
}
drug_likeness_metric = [drug_likeness_parser[i] for i in contents['scoring_function'] if '.h5' not in i]

vocab = pd.read_csv('../preprocessor/vocab.csv')['tokens'].to_list()
tokenizer = {i : n for n, i in enumerate(vocab)}

potential_models = [i for i in contents['scoring_function'] if '.h5' in i]
if len(potential_models) > 0:
    models_array = [models.load_model(i) for i in potential_models]
    print('Compiling models...')
    [model.compile() for model in models_array]
    max_len = contents['max_len']
    seq_shape = np.array([max_len, np.max([i+1 for i in tokenizer.values()])+1], dtype=np.int32)
    model_pred = True
else:
    model_pred = False

# potentially can leave this with a bunch of setup args (tokenizer, seq_shape, model_array)
def ensemble_predict(tokens):
    initial_seq = np.array([tokenizer[i]+1 for i in tokens])
    full_seq = np.hstack([np.zeros(max_len-len(initial_seq)), initial_seq])
    full_seq = seqOneHot(np.array(full_seq, dtype=np.int32), seq_shape).reshape(1, *seq_shape)
    
    return np.hstack([i.predict(full_seq, verbose=0) for i in models_array])

def augment_smiles(string, n):
    sme = SmilesEnumerator()
    output = []
    for i in range(n):
        output.append(sme.randomize_smiles(string))
    
    return output

def get_augs(string, n):
    strings = [string] + augment_smiles(string, n)
    tokens_array = [return_tokens(i, vocab)[0] for i in strings]

    full_seqs = []
    for tokens in tokens_array:
        if any([i not in vocab for i in tokens]):
            continue
        
        initial_seq = np.array([tokenizer[n]+1 for n in tokens])
        full_seq = np.hstack([np.zeros(max_len-len(initial_seq)), initial_seq])
        full_seq = seqOneHot(np.array(full_seq, dtype=np.int32), seq_shape).reshape(1, *seq_shape)
        full_seqs.append(full_seq[0])

        ####################################################################################
        # may want to reformat to while loop to see if we can still reach n many compounds #
        ####################################################################################

    return np.array(full_seqs)

@lru_cache(maxsize=256)
def no_model_scoring(string, target):
    raw_return = return_tokens(string, vocab)
    isNotValidToken = raw_return[1]

    if isNotValidToken:
        return -100
    else:
        molecule = Chem.MolFromSmiles(string)
        likeness_score = np.array(np.hstack([metric(molecule) for metric in drug_likeness_metric]))
        return -1 * get_score(likeness_score, np.array(target))

@lru_cache(maxsize=256)
def model_scoring(string, scoring_args):
    target, aug, num_of_augments = scoring_args

    raw_return = return_tokens(string, vocab)
    isNotValidToken = raw_return[1]
    tokens = raw_return[0]
    if isNotValidToken:
        return -100

    molecule = Chem.MolFromSmiles(string)
    likeness_score = np.array(np.hstack([metric(molecule) for metric in drug_likeness_metric]))
    
    if not aug:
        pred = ensemble_predict(tokens)[0]
        return -1 * get_score(np.hstack([pred, likeness_score]), np.array(target))
    else:
        augs = get_augs(string, num_of_augments)        
        pred = np.hstack([i.predict(augs, verbose=0) for i in models_array]).sum(axis=0) / len(augs)
        return  -1 * get_score(np.hstack([pred, likeness_score]), np.array(target))

scoring_args = contents['target']

if len(scoring_args) != len(potential_models) * 2 + len(drug_likeness_metric):
    print(f'{RED}Target arugment does not match scoring functions{NC}')
    sys.exit(1)
if [i for i in scoring_args if not 0 <= i <= 1]:
    print(f"{RED}Target must be between 0 and 1{NC}")
    sys.exit(1)

if model_pred:
    scoring_args = [scoring_args]
    if contents['augment'][0]:
        scoring_args.append(contents['augment'][0])
        scoring_args.append(contents['augment'][1])
    else:
        scoring_args.append(False)
        scoring_args.append(0)
    scoring_args[0] = tuple(scoring_args[0])

    scoring_function = model_scoring
else:
    scoring_function = no_model_scoring

scoring_args = tuple(scoring_args)

string_ga.co.average_size = contents['average_size']
string_ga.co.size_stdev = contents['size_stdev']
string_ga.co.string_type = contents['string_type']

print('Starting GA...')

(scores, population, high_scores, generation) = string_ga.GA([contents['population_size'], contents['file_name'], 
                                       scoring_function, contents['generations'],
                                       contents['mating_pool_size'], contents['mutation_rate'], 
                                       scoring_args, contents['max_score'],
                                       contents['prune_population'], contents['seed']])

final_result_df = pd.DataFrame(set(high_scores))
final_result_df.columns = ['score', 'string']
final_result_df.sort_values(by='score', ascending=False)
final_result_df.to_csv(sys.argv[2], index=False)

print(f'{GREEN}Wrote molecules to file{NC}')
