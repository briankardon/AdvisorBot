import re
import urllib as UL
import xml.etree.ElementTree as ET
import datetime
import sqlite3 as sq
import os

# These are internal namespace identifiers used by the arXiv XML metadata generator
baseURL = 'http://export.arxiv.org/oai2'
baseQuery = '?verb=GetRecord&metadataPrefix=arXiv&identifier=oai:arXiv.org:'

metadataDir = './metadata/'

# Load and return a ranked dictionary of the 1000 most common words in the English language from a given file
def loadCommon(filename="common.txt"):
	f = open(filename, 'r')
	common = {}
	for line in f:
		common[line.split(":")[0]] = line.split(":")[1]
	return common

# Download the metadata from arXiv for the specified article.  
# The article may be specified by month + year + ID or by a full arXiv identifier string.
# To be polite to arXiv's servers, if the requested article exists in the metadataDir subdirectory, then it is downloaded and saved.  If it DOES exist, then it is not re-downloaded, but instead loaded from the local file.  This behavior can be disabled by setting the "saveLocalCopy" and/or "useLocalCopy" flags to False
def downloadMetadata(year='13', month='01', articleNum='0001', identifier=None, allowFutureYears=False, saveLocalCopy=True, useLocalCopy=True):
	if identifier is None:
		if len(year) <> 2:
			print "Bad year format."
			return
		if len(month) <> 2:
			print "Bad month format."
			return
		if len(articleNum) < 4:
			articleNum = '0'*(4-len(articleNum)) + articleNum
		if len(articleNum) > 4:
			print "Bad article format."
			return
		if int(articleNum) > 9999:
			print "Bad article number -", articleNum, ".  Article number must be between 0 and 10,000"
			return
		if not allowFutureYears and (int(year) < 7 or int(year)> str(datetime.datetime.now().year)[2:]):
			print "Year out of range."
			return
		if int(month) < 1 or int(month) > 12:
			print "Month out of range."
			return
		identifier = year+month+'.'+articleNum
	if useLocalCopy and (identifier+'.xml') in os.listdir(metadataDir):
		if not os.path.isdir(metadataDir): os.mkdir(metadataDir)
		hf = open(metadataDir+identifier+'.xml')
		saveLocalCopy = False
	else:
		hf = UL.urlopen(baseURL+baseQuery+identifier)
	articleXML = hf.read()
	if saveLocalCopy:
		if not os.path.isdir(metadataDir): os.mkdir(metadataDir)
		pf = open(metadataDir + identifier + '.xml', 'w')
		pf.write(articleXML)
		pf.close()
	hf.close()
	return articleXML

# This function takes a string (such as an article abstract) and attempts to remove as much punctuation and extra whitespace and then assembles a list of unique words
def getWords(text):
	words = []
	disallowedWords = ["\"", "\'", "[", "]", "{", "}", "(", ")", ",", ".", ";", ":", "<", ">", "?", "/", "\\"] + [str(x) for x in range(0, 10)]
	text = re.sub(r'\t' , r' ', text)
	text = re.sub(r'\ ([^a-zA-Z0-9]+)', r' \1 ', text)
	text = re.sub(r'([^a-zA-Z0-9]+)\ ', r' \1 ', text)
	text = text.replace('\n', ' ')
	text = re.sub(r'\ +', r' ', text)
	text = text.lower()
	text = text.split(" ")
	for w in text:
		if w not in words and len(w) > 0 and w not in disallowedWords and not any([x in w for x in disallowedWords]):
			words.append(w)
	return words

# This function takes the XML metadata file that arXiv serves up, and parses out the information into a dictionary.
def parseArticleXML(article):
	OAI_prefix = '{http://www.openarchives.org/OAI/2.0/}'
	arXiv_prefix = '{http://arxiv.org/OAI/arXiv/}'
	dataTree = ET.fromstring(article)
#	authors = [ for in dataTree]
	error = dataTree.find(OAI_prefix + 'error')
	if error is not None and error.attrib['code'] == 'idDoesNotExist':
		print "Article does not exist"
		return
	GetRecord = dataTree.find(OAI_prefix + 'GetRecord')
	record = GetRecord.find(OAI_prefix + 'record')
	metadata = record.find(OAI_prefix + 'metadata').find(arXiv_prefix + 'arXiv')
	authors = [] 
	for a in metadata.find(arXiv_prefix + 'authors').findall(arXiv_prefix + 'author'):
		forenames = a.find(arXiv_prefix + 'forenames')
		if forenames is None:
			forenames = ""
		else:
			forenames = forenames.text + " "
		keyname = a.find(arXiv_prefix + 'keyname').text
		authors.append(forenames + keyname)
	date = metadata.find(arXiv_prefix + "created").text
	title = metadata.find(arXiv_prefix + "title").text
	categories = [category.split(".")[0] for category in metadata.find(arXiv_prefix + "categories").text.split(" ")]
	subCategories = [category.split(".")[1] for category in filter(lambda x:('.' in x), metadata.find(arXiv_prefix + "categories").text.split(" "))]
	abstract = re.sub(' {2,}', ' ', re.sub('\n', ' ', metadata.find(arXiv_prefix + "abstract").text))
	abstractWords = getWords(abstract)
	titleWords = getWords(title)
#	print "% common words: ", float(sum([(w in common) for w in words]))/len(words)
	commonWords = filter(lambda x:(x in common), abstractWords)
	uncommonAbstractWords = filter(lambda x:(not (x in common)), abstractWords)
	uncommonTitleWords = filter(lambda x:(not (x in common)), titleWords)
	return {'title':title, 'date':date, 'authors':authors, 'abstract':abstract, 'categories':categories, 'subCategories':subCategories, 'uncommonAbstractWords':uncommonAbstractWords, 'uncommonTitleWords':uncommonTitleWords}

# Compares two articles and gives them a score indicating how related those two articles are (under development)
def compareArticles(parsedArticle1, parsedArticle2):
	score = 0
	uncommonTitleMatch = 10
	uncommonAbstractMatch = 1
	authorMatch = 15
	categoryMatch = 100
	subCategoryMatch = 100
	
#	for word in parsedArticle1['uncommonAbstractWords']:
#		if word in parsedArticle2['uncommonAbstractWords']:
#			score += uncommonAbstractMatch
	ac1 = dict(autocorrelate(parsedArticle1['title'] + parsedArticle1['abstract'], excludedWords=common, kernels=[3]))
	ac2 = dict(autocorrelate(parsedArticle2['title'] + parsedArticle2['abstract'], excludedWords=common, kernels=[3]))
	for word1 in ac1:
		if word1 in ac2:
			score += uncommonAbstractMatch*ac1[word1]*ac2[word1]
	print "score after ac matching:", score
	for word in parsedArticle1['uncommonTitleWords']:
		if word in parsedArticle2['uncommonTitleWords']:
			score += uncommonTitleMatch
	for category in parsedArticle1['categories']:
		if category in parsedArticle2['categories']:
			score += categoryMatch
	for subCategory in parsedArticle1['subCategories']:
		if subCategory in parsedArticle2['subCategories']:
			score += subCategoryMatch
	print "overall score", score
	
	maxScore = uncommonTitleMatch*min([len(parsedArticle1['uncommonTitleWords']), len(parsedArticle2['uncommonTitleWords'])]) + uncommonAbstractMatch*min([len(ac1), len(ac2)]) + categoryMatch * min([len(parsedArticle1['categories']), len(parsedArticle2['categories'])]) + subCategoryMatch * min([len(parsedArticle1['subCategories']), len(parsedArticle2['subCategories'])])
#	print score, maxScore
	return float(score)/maxScore

# Autocorrelates a body of text, and ranks the unique words within that text by how much they contain a patterns that repeat in the text (intended to pick out words with frequently-used roots, such as the word "gravity" in an article with words like "gravitational", "graviton", "gravitometric", etc
def autocorrelate(text, excludedWords=[], kernels=[3]):
	az = re.compile('[^a-zA-Z\-\ ]')
	text = text.lower()
	text = re.sub(az, '', text)
	l = len(text)
	scores = [0]*l
	for k in kernels:
		for n in range(0, len(text)-k):
			for m in [x % l for x in range(n, (n + l - k))]:
#				print text[n:n+k], text[m:m+k]
				if text[n:n+k] == text[m:m+k]:
					scores[n] += 1
	wc = 0
	words = text.split(" ")
	wordScores = [0]*len(words)
	for k in range(0, len(scores)):
		if text[k] == " ":
			wc += 1
			continue
		wordScores[wc] += scores[k]
	wordScores = [wordScores[k]/((1.0+len(words[k])) * (1.0 + len(words)) + (1.0 + len(kernels))) for k in range(0, len(wordScores))]
	result = zip(words, wordScores)
	result = filter(lambda x:(x[0] not in excludedWords), result)
	combinedWordScores = {}
	for word, score in result:
		if word not in combinedWordScores:
			combinedWordScores[word] = score
		else:
			combinedWordScores[word] += score
	maxScore = max([combinedWordScores[x] for x in combinedWordScores])
	return sorted([(k, v*1.0/maxScore) for k, v in combinedWordScores.iteritems()], key=lambda x:-x[1])



#This is the sandbox area, for testing:

common = loadCommon()

scores = {}
for num in range(1, 100):
	print "downloading article #"+str(num)
	a1 = parseArticleXML(downloadMetadata(articleNum=str(10)))
	a2 = parseArticleXML(downloadMetadata(articleNum=str(num)))
	score = compareArticles(a1, a2)
	scores[num] = score
print scores

besties = sorted(scores.keys(), key=lambda x: -scores[x])
print besties

#for num in range(10, 30):
#	a = parseArticleXML(downloadMetadata(articleNum=str(num)))
#	print
#	print a['abstract']
#	print
#	print autocorrelate(a["title"] + " " + a["abstract"], kernels=[4], excludedWords=loadCommon().keys())
#	print
#	print "********************************************************************************"

#def compareArticlesOld(parsedArticle1, parsedArticle2):
#	score = 0
#	uncommonTitleMatch = 10
#	uncommonAbstractMatch = 1
#	authorMatch = 15
#	categoryMatch = 100
#	subCategoryMatch = 100
#	
#	for word in parsedArticle1['uncommonAbstractWords']:
#		if word in parsedArticle2['uncommonAbstractWords']:
#			score += uncommonAbstractMatch
#	for word in parsedArticle1['uncommonTitleWords']:
#		if word in parsedArticle2['uncommonTitleWords']:
#			score += uncommonTitleMatch
#	for category in parsedArticle1['categories']:
#		if category in parsedArticle2['categories']:
#			score += categoryMatch
#	for subCategory in parsedArticle1['subCategories']:
#		if subCategory in parsedArticle2['subCategories']:
#			score += subCategoryMatch
#	
#	maxScore = uncommonTitleMatch*min([len(parsedArticle1['uncommonTitleWords']), len(parsedArticle2['uncommonTitleWords'])]) + uncommonAbstractMatch*min([len(parsedArticle1['uncommonAbstractWords']), len(parsedArticle2['uncommonAbstractWords'])]) + categoryMatch * min([len(parsedArticle1['categories']), len(parsedArticle2['categories'])]) + subCategoryMatch * min([len(parsedArticle1['subCategories']), len(parsedArticle2['subCategories'])])
##	print score, maxScore
#	return float(score)/maxScore

