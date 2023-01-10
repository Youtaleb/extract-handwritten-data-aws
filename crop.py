from PyPDF2 import PdfWriter, PdfReader
from pathlib import Path
from decimal import Decimal
import json
import os
import math
import sys

# Get the pdf file
pdf_path = Path(sys.argv[2])
# Get the json file
json_path = Path(sys.argv[3])

class Box():
    """
    This object will define the central elements of this script, which is the notion of boxes :
    AWS Textract logic revolves around outputing boxes encapsulating the words it has detects in the input document.
    """
    def __init__(self,width,height,left,top,page_width,page_height):
        self.width = float(width)
        self.height = float(height)
        self.left = float(left)
        self.top = float(top)
        self.page_width = float(page_width)
        self.page_height = float(page_height)

        # In AWS textract, width,height,left,top are in %. They represent the % of the dimensions of the whole page.
        self.left = self.page_width * self.left
        self.top = self.page_height * self.top
        self.width = self.page_width * self.width
        self.height = self.page_height * self.height

        self.lowerLeft = (int(self.left), int(self.page_height-self.top-self.height))
        self.upperRight = (int(self.left + self.width), int(self.page_height-self.top))

        # self.lowerLeft = (int(math.ceil(self.left)), int(math.ceil(self.page_height-self.top-self.height)))
        # self.upperRight = (int(math.ceil(self.left + self.width)), int(math.ceil(self.page_height-self.top)))

    def top_midpoint(self):
        return (self.left+self.width/2,self.page_height-self.top)

    def bottom_midpoint(self):
        return (self.left+self.width/2,self.page_height-self.top-self.height)

    def __str__(self):
        return f"Box(width: {self.width}, Height: {self.height}, Left: {self.left}, Top: {self.top}, Page width: {self.page_width}, Page height: {self.page_height}, Lower left: {self.lowerLeft}, Upper right: {self.upperRight})"


def select_first_page(doc_path):
    """
    For some reason, PyPDF2 generates extra blank pages after cropping.
    The function below cleans the generated document by removing the blank pages : it selects only the first page.
    """
    input_pdf = PdfReader(str(Path(doc_path)))
    first_page = input_pdf.getPage(0)
    pdf_writer = PdfWriter()
    pdf_writer.addPage(first_page)
    with Path(doc_path).open(mode="wb") as doc_path:
        pdf_writer.write(doc_path)

def find_boxes(key_word,aws_data):
    """
    This function returns the boxes' IDs of the elements we are trying to find in our document.
    key_word represents the word (of type string) that we are looking for in the document, for example "fatturato".
    doc_path represents the path of the document on which the search is performed.

    """

    boxes_id_page = dict() # The dict containing the IDs of the boxes of the searched term.

    for i in range(len(aws_data["Blocks"])):
        if "Text" in aws_data["Blocks"][i] and str.lower(key_word) in str.lower(aws_data["Blocks"][i]['Text']):
            boxes_id_page[aws_data["Blocks"][i]['Id']] = aws_data["Blocks"][i]['Page']

    if not boxes_id_page:
            print("The word "+str(key_word)+" has not been detected in the document.")

    #*!!!TEST!!!*#
    # print(aws_data["Blocks"][45]) # First "FATTURATO" occurence
    #print(len(boxes_id))
    return boxes_id_page

def find_bounding_box(box_id,aws_data):
    """
    This function returns the bounding box with a given ID.
    We recall that every box is uniquely determined by its ID.
    bb = bounding box.
    """
    bb = dict() # Dictionnary to contain the Bounding Box.
    for i in range(len(aws_data["Blocks"])):
        if aws_data["Blocks"][i]['Id'] == box_id:
            #print("ID FOUND!")
            bb = aws_data["Blocks"][i]['Geometry']['BoundingBox']
            break
    else:
        print("The ID given doesn't correspond to any box.")

    return bb

def crop_box(box_id,box_name,aws_data,page,page_width,page_height,writer):
    """
    This function crops a box given its ID.
    """
    bounding_box = find_bounding_box(box_id,aws_data)

    box = Box(bounding_box['Width'],bounding_box['Height'],bounding_box['Left'],bounding_box['Top'],page_width,page_height)

    page.mediaBox.lowerLeft = box.lowerLeft
    page.mediaBox.upperRight = box.upperRight

    writer.add_page(page)

    output_file_name = box_name

    with open(output_file_name, "wb") as fp:
        writer.write(fp)

    select_first_page(output_file_name)

def neighbourhood_box(box_id,aws_data,page_width,page_height,loc):
    """
    Detect the neighbourhood of a box.
    """
    #*!!!!!!!!!!*#
    scope_neighbourhood = 12 # represents how many boxes we select after the box in question.
    neighbourhood_boxes = []
    for i in range(len(aws_data["Blocks"])):
        if "Text" in aws_data["Blocks"][i] and aws_data["Blocks"][i]["Id"] == box_id:
            for j in range(i-1,i+scope_neighbourhood): #the range starts at i-1, which corresponds to the element before our box
                neighbourhood_boxes.append(aws_data["Blocks"][j]['Id'])

    boxes = dict() #contains the boxes in the neighbourhood of our box.
    if loc == "l":
        main_box = boxes[box_id]
        bounding_box = find_bounding_box(neighbourhood_boxes[0],aws_data)
        neighbourhood_box_left = Box(bounding_box['Width'],bounding_box['Height'],bounding_box['Left'],bounding_box['Top'],page_width,page_height)

        if 0.8*main_box.height+main_box.top < neighbourhood_box_left.top < 1.2*main_box.height+main_box.top:
            return neighbourhood_boxes[0]

    elif loc == "r":
        return neighbourhood_boxes[2]
    elif loc == "b":
        for id in neighbourhood_boxes:
            bounding_box = find_bounding_box(id,aws_data)
            box = Box(bounding_box['Width'],bounding_box['Height'],bounding_box['Left'],bounding_box['Top'],page_width,page_height)
            boxes[id] = box

        neighbourhood_boxes_dist = {} # dict containing the distances between the main box and the boxes below it.
        for id in neighbourhood_boxes:
            main_box = boxes[box_id]
            neighbourhood_box = boxes[id]
            #if neighbourhood_box.top > main_box.top+0.2*main_box.height:
            if neighbourhood_box.top > main_box.top:
                neighbourhood_boxes_dist[id] = math.dist( main_box.bottom_midpoint() , neighbourhood_box.top_midpoint() )

        return min(neighbourhood_boxes_dist, key=neighbourhood_boxes_dist.get)

    else:
        print("Something went wrong while detecting the neighborhood of the key word!")

def crop(key_word,pdf_path,json_path):
    """
    This function crops the key word whenever it finds in the document.
    The mediaBox attribute represents a rectangular area defining the boundaries of the page.
    """

    # Check if the pdf file and json file exist
    if os.path.exists(pdf_path) and os.path.exists(json_path):
        reader = PdfReader(pdf_path)
        writer = PdfWriter()

        try:
            with open(json_path, 'r') as aws_output:
                # Convert JSON file to dictionary in Python
                aws_data = json.load(aws_output)

            for k in range(reader.getNumPages()): # k represents the page's number
                page = reader.pages[k]
                #print(reader.getNumPages())

                page_width = float(page.mediaBox.lowerRight[0])
                page_height = float(page.mediaBox.upperLeft[1])

                i=1
                for id in find_boxes(key_word,aws_data).keys():
                    if int(find_boxes(key_word,aws_data)[id]) == k+1:
                        crop_box(id,"./output/page_"+str(k+1)+"_"+key_word+"_"+str(i)+".pdf",aws_data,page,page_width,page_height,writer)

                        id_box_below = neighbourhood_box(id,aws_data,page_width,page_height,"b")
                        crop_box(id_box_below,"./output/page_"+str(k+1)+"_"+key_word+"_"+str(i)+"_bottom"+".pdf",aws_data,page,page_width,page_height,writer)

                        i+=1 # i is involved in naming the document.

        except:
            print("A problem reading the JSON file has been detected.")

    else:
        if not os.path.exists(pdf_path):
            print('The file '+str(pdf_path)+' does NOT exist.')
        if not os.path.exists(json_path):
            print('The file '+str(json_path)+' does NOT exist.')

crop(sys.argv[1],pdf_path,json_path)
