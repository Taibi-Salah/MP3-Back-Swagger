<?php

namespace App\Controller;

use App\Entity\Mp3File;
use Doctrine\ORM\EntityManagerInterface;
use Symfony\Bundle\FrameworkBundle\Controller\AbstractController;
use Symfony\Component\HttpFoundation\Request;
use Symfony\Component\HttpFoundation\Response;
use Symfony\Component\Routing\Annotation\Route;
use Psr\Log\LoggerInterface;
use Symfony\Component\HttpFoundation\Session\SessionInterface;
use Symfony\Component\HttpFoundation\BinaryFileResponse;
use Symfony\Component\HttpFoundation\ResponseHeaderBag;
use Symfony\Component\String\Slugger\SluggerInterface;
use Symfony\Component\Routing\Generator\UrlGeneratorInterface;
use OpenApi\Annotations as OA;

class HomeController extends AbstractController
{
    private LoggerInterface $logger;
    private const CONVERSION_LIMIT = 5;
    private const MP3_DIRECTORY = '/var/www/html/MP3_MUSICS/';

    public function __construct(LoggerInterface $logger)
    {
        $this->logger = $logger;
    }

    #[Route('/api', name: 'api_home', methods: ['GET'])]
    public function apiHome(Request $request, EntityManagerInterface $entityManager, SluggerInterface $slugger, SessionInterface $session): Response
    {
        $url = $request->query->get('url');
        $error = null;
        $conversion_status = null;
        $download_link = null;
        $mp3FileName = null;

        $conversionCount = $session->get('conversion_count', 0);

        if ($url) {
            if ($conversionCount >= self::CONVERSION_LIMIT) {
                $error = "You have reached the maximum number of free conversions. Please subscribe to our premium service for unlimited conversions.";
            } else {
                try {
                    if (!is_dir(self::MP3_DIRECTORY)) {
                        mkdir(self::MP3_DIRECTORY, 0777, true);
                    }

                    $videoInfo = $this->getVideoInfo($url);
                    $safeTitle = $slugger->slug($videoInfo['title']);
                    $mp3FileName = $safeTitle . '-' . $videoInfo['id'] . '.mp3';
                    $mp3FilePath = self::MP3_DIRECTORY . $mp3FileName;

                    $this->convertYoutubeToMp3($url, $mp3FilePath);

                    $this->logger->info('File created at: ' . $mp3FilePath);

                    // Save to database
                    $mp3File = new Mp3File();
                    $mp3File->setMp3File($mp3FileName);
                    $mp3File->setYoutubeUrl($url);
                    $mp3File->setTitle($videoInfo['title']);
                    $mp3File->setFilePath($mp3FilePath);

                    $entityManager->persist($mp3File);
                    $entityManager->flush();

                    $this->logger->info('Mp3File entity persisted: ' . json_encode([
                        'mp3FileName' => $mp3FileName,
                        'youtubeUrl' => $url,
                        'title' => $videoInfo['title'],
                        'filePath' => $mp3FilePath,
                    ]));

                    $conversion_status = "Vidéo convertie avec succès en MP3 !";
                    $download_link = $this->generateUrl('download_mp3', ['filename' => $mp3FileName]);
                    $this->logger->info('Download link generated: ' . $download_link);

                    $session->set('conversion_count', $conversionCount + 1);
                } catch (\Exception $e) {
                    $this->logger->error('Conversion error: ' . $e->getMessage());
                    $error = "Une erreur est survenue lors de la conversion : " . $e->getMessage();
                }
            }
        } else {
            $error = "Veuillez fournir une URL valide.";
        }

        return $this->json([
            'error' => $error,
            'conversion_status' => $conversion_status,
            'download_link' => $download_link,
            'mp3FileName' => $mp3FileName,
            'title' => $videoInfo['title'] ?? null
        ]);
    }

    #[Route('/api/music', name: 'api_music', methods: ['GET'])]
    public function getAllMusic(EntityManagerInterface $entityManager): Response
    {
        $repository = $entityManager->getRepository(Mp3File::class);
        $mp3Files = $repository->findAll();

        $data = [];
        foreach ($mp3Files as $mp3File) {
            $data[] = [
                'mp3FileName' => $mp3File->getMp3File(),
                'youtubeUrl' => $mp3File->getYoutubeUrl(),
                'title' => $mp3File->getTitle(),
                'filePath' => $mp3File->getFilePath(),
                'downloadLink' => $this->generateUrl('download_mp3', ['filename' => $mp3File->getMp3File()], UrlGeneratorInterface::ABSOLUTE_URL),
            ];
        }

        return $this->json($data);
    }

    #[Route('/download/{filename}', name: 'download_mp3')]
    public function downloadMp3($filename): Response
    {
        $filePath = self::MP3_DIRECTORY . $filename;
        
        if (!file_exists($filePath)) {
            throw $this->createNotFoundException('The file does not exist');
        }

        return $this->file($filePath);
    }

    // Add this method to fetch video information
    private function getVideoInfo(string $url): array
    {
        $this->logger->info('Fetching video info for URL: ' . $url);
        
        // Use yt-dlp to fetch video information
        $command = sprintf('yt-dlp --dump-json "%s" 2>&1', $url);
        $this->logger->info('Executing command: ' . $command);
        
        exec($command, $output, $return_var);
        
        $this->logger->info('yt-dlp output: ' . implode("\n", $output));
        $this->logger->info('yt-dlp return code: ' . $return_var);

        if ($return_var !== 0) {
            throw new \Exception('Error fetching video info: ' . implode("\n", $output));
        }

        $videoInfo = json_decode(implode("\n", $output), true);

        if (json_last_error() !== JSON_ERROR_NONE) {
            throw new \Exception('Error decoding JSON: ' . json_last_error_msg());
        }

        return [
            'id' => $videoInfo['id'],
            'title' => $videoInfo['title']
        ];
    }

    // Add this method to convert YouTube video to MP3
    private function convertYoutubeToMp3(string $url, string $outputPath): void
    {
        $command = sprintf('yt-dlp --extract-audio --audio-format mp3 --output "%s" "%s" 2>&1', $outputPath, $url);
        $this->logger->info('Executing command: ' . $command);
        
        exec($command, $output, $return_var);
        
        $this->logger->info('yt-dlp output: ' . implode("\n", $output));
        $this->logger->info('yt-dlp return code: ' . $return_var);

        if ($return_var !== 0) {
            throw new \Exception('Error converting video to MP3: ' . implode("\n", $output));
        }
    }
}


